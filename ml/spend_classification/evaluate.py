# Databricks notebook source
# MAGIC %md
# MAGIC # Spend classification — evaluation across slices, 2-tier metrics
# MAGIC
# MAGIC Compares all registered model aliases of `<catalog>.ml.spend_classifier`
# MAGIC (`@challenger`, optionally `@challenger_embedding`) against a synthetic
# MAGIC `gl_account → most-common-leaf` baseline. Reports both leaf-tier
# MAGIC (`secondary`) and parent-tier (`primary`) metrics on two slices:
# MAGIC
# MAGIC | Slice | Source | Purpose |
# MAGIC |---|---|---|
# MAGIC | Holdout | `<catalog>.ml.spend_clf_holdout` | Primary accuracy metric |
# MAGIC | Maverick holdout | `<catalog>.ml.spend_clf_maverick_holdout` | The hard-case slice |
# MAGIC
# MAGIC Writes each run's metrics to `<catalog>.ml.spend_clf_eval_runs` (append),
# MAGIC then promotes the winning model to `@production`. Winner = highest
# MAGIC `secondary_top1_accuracy` on the maverick slice; ties broken by holdout
# MAGIC `secondary_top1_accuracy`.
# MAGIC
# MAGIC The trained pyfunc returns a DataFrame with all four prediction columns;
# MAGIC this notebook just compares `predicted_secondary_category` vs the truth
# MAGIC `label` and `predicted_primary_category` vs `label_primary`.

# COMMAND ----------
dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema_ml", "")
dbutils.widgets.text("schema_gold", "gold")
dbutils.widgets.text("model_name", "spend_classifier")

catalog = dbutils.widgets.get("catalog")
schema_ml = dbutils.widgets.get("schema_ml")
schema_gold = dbutils.widgets.get("schema_gold")
model_name = dbutils.widgets.get("model_name")

uc_model = f"{catalog}.{schema_ml}.{model_name}"
eval_runs_fqn = f"`{catalog}`.`{schema_ml}`.spend_clf_eval_runs"
print(f"Evaluating aliases of {uc_model}")
print(f"Eval results table: {eval_runs_fqn}")

# COMMAND ----------
# MAGIC %md ## Load eval slices + taxonomy

# COMMAND ----------
import numpy as np
import pandas as pd
from datetime import datetime

TEXT_COL = "line_description"
CAT_COLS = ["supplier_id", "segment_code", "payment_terms", "currency",
            "supplier_region", "gl_account", "direct_indirect",
            "addressability", "category_primary_hint"]
NUM_COLS = ["log_amount", "log_quantity", "log_unit_price",
            "supplier_maverick_propensity"]
FEATURE_COLS = [TEXT_COL] + CAT_COLS + NUM_COLS


def load_slice(table_name: str) -> pd.DataFrame:
    sdf = spark.table(f"`{catalog}`.`{schema_ml}`.{table_name}")
    pdf = sdf.toPandas()
    for c in CAT_COLS:
        pdf[c] = pdf[c].fillna("__NA__").astype(str)
    pdf[TEXT_COL] = pdf[TEXT_COL].fillna("").astype(str)
    for c in NUM_COLS:
        pdf[c] = pd.to_numeric(pdf[c], errors="coerce").fillna(0.0)
    pdf["label"] = pdf["label"].astype(str)
    pdf["label_primary"] = pdf["label_primary"].astype(str)
    return pdf


holdout_pdf = load_slice("spend_clf_holdout")
maverick_pdf = load_slice("spend_clf_maverick_holdout")
train_pdf = load_slice("spend_clf_train")
print(f"holdout: {len(holdout_pdf):,} | maverick: {len(maverick_pdf):,} | train (for baseline only): {len(train_pdf):,}")

# Leaf → Parent map from the UC taxonomy (matches what the wrapped model learned)
taxonomy_pdf = (spark.table(f"`{catalog}`.`{schema_gold}`.dim_spend_category")
                     .select("secondary_code", "primary_code")
                     .toPandas())
leaf_to_parent = dict(zip(taxonomy_pdf["secondary_code"], taxonomy_pdf["primary_code"]))
print(f"Taxonomy: {len(leaf_to_parent)} leaves × {len(set(leaf_to_parent.values()))} parents")

# COMMAND ----------
# MAGIC %md ## Build the GL-account baseline
# MAGIC
# MAGIC `gl_account → most-common leaf in training set`. This is the sanity floor
# MAGIC the model must beat. Because the generator deterministically maps
# MAGIC `category → gl_account`, the baseline is genuinely strong — beating it by
# MAGIC ≥ 10 pp on the leaf tier is the demo-narrative target.

# COMMAND ----------
gl_to_leaf = (train_pdf.groupby("gl_account")["label"]
                       .agg(lambda s: s.mode().iloc[0])
                       .to_dict())
global_leaf_fallback = train_pdf["label"].mode().iloc[0]
print(f"GL baseline: {len(gl_to_leaf)} known gl_account values; fallback leaf = {global_leaf_fallback}")


def gl_baseline_predict_leaf(df: pd.DataFrame) -> np.ndarray:
    return df["gl_account"].map(lambda g: gl_to_leaf.get(g, global_leaf_fallback)).values


# COMMAND ----------
# MAGIC %md ## Discover model aliases under evaluation

# COMMAND ----------
import mlflow
from mlflow.tracking import MlflowClient

mlflow.set_registry_uri("databricks-uc")
client = MlflowClient(registry_uri="databricks-uc")

# We always evaluate @challenger; @challenger_embedding is optional (skip if absent).
candidate_aliases = ["challenger", "challenger_embedding"]
present_aliases = []
for alias in candidate_aliases:
    try:
        client.get_model_version_by_alias(uc_model, alias)
        present_aliases.append(alias)
        print(f"  ✓ {uc_model}@{alias}")
    except Exception as e:
        print(f"  · skipping {uc_model}@{alias} (not found: {e.__class__.__name__})")

assert present_aliases, (
    f"No registered models found under {uc_model} — run train_baseline.py first."
)

# COMMAND ----------
# MAGIC %md ## Score every model × every slice

# COMMAND ----------
from sklearn.metrics import accuracy_score, f1_score


def score_predictions(y_true_leaf, y_pred_leaf, y_true_parent, y_pred_parent, n_rows, model_alias, slice_name):
    return {
        "model_alias": model_alias,
        "slice": slice_name,
        "secondary_top1_accuracy": float(accuracy_score(y_true_leaf,   y_pred_leaf)),
        "primary_top1_accuracy":   float(accuracy_score(y_true_parent, y_pred_parent)),
        "secondary_macro_f1":      float(f1_score(y_true_leaf,   y_pred_leaf,   average="macro", zero_division=0)),
        "primary_macro_f1":        float(f1_score(y_true_parent, y_pred_parent, average="macro", zero_division=0)),
        "n_rows": int(n_rows),
    }


results = []

for slice_name, df in [("holdout", holdout_pdf), ("maverick_holdout", maverick_pdf)]:
    X = df[FEATURE_COLS]
    y_leaf = df["label"].values
    y_parent = df["label_primary"].values

    # MLflow-registered model aliases
    for alias in present_aliases:
        model_uri = f"models:/{uc_model}@{alias}"
        model = mlflow.pyfunc.load_model(model_uri)
        preds = model.predict(X)
        # The pyfunc returns a DataFrame with the 4-col schema; mlflow.pyfunc.load_model
        # is lenient with the output type so coerce defensively.
        preds_df = pd.DataFrame(preds)
        y_pred_leaf = preds_df["predicted_secondary_category"].astype(str).values
        y_pred_parent = preds_df["predicted_primary_category"].astype(str).values
        results.append(score_predictions(
            y_leaf, y_pred_leaf, y_parent, y_pred_parent,
            n_rows=len(df), model_alias=alias, slice_name=slice_name,
        ))

    # GL-account baseline (built in-notebook — not an MLflow model)
    y_pred_leaf_b = gl_baseline_predict_leaf(df)
    y_pred_parent_b = np.array([leaf_to_parent.get(l, "UNKNOWN") for l in y_pred_leaf_b])
    results.append(score_predictions(
        y_leaf, y_pred_leaf_b, y_parent, y_pred_parent_b,
        n_rows=len(df), model_alias="gl_account_baseline", slice_name=slice_name,
    ))

eval_pdf = pd.DataFrame(results)
print("Eval results:")
print(eval_pdf.to_string(index=False))

# COMMAND ----------
# MAGIC %md ## Persist eval results to `<catalog>.ml.spend_clf_eval_runs`

# COMMAND ----------
from pyspark.sql import functions as F
from pyspark.sql.types import (StructType, StructField, StringType,
                               DoubleType, IntegerType, TimestampType)

eval_pdf["evaluated_at"] = datetime.utcnow()
eval_pdf["uc_model"] = uc_model

# Explicit schema — avoid inferred Long vs Int drift when appending
eval_schema = StructType([
    StructField("model_alias",             StringType(),    True),
    StructField("slice",                   StringType(),    True),
    StructField("secondary_top1_accuracy", DoubleType(),    True),
    StructField("primary_top1_accuracy",   DoubleType(),    True),
    StructField("secondary_macro_f1",      DoubleType(),    True),
    StructField("primary_macro_f1",        DoubleType(),    True),
    StructField("n_rows",                  IntegerType(),   True),
    StructField("evaluated_at",            TimestampType(), True),
    StructField("uc_model",                StringType(),    True),
])

eval_sdf = spark.createDataFrame(eval_pdf[
    ["model_alias", "slice", "secondary_top1_accuracy", "primary_top1_accuracy",
     "secondary_macro_f1", "primary_macro_f1", "n_rows", "evaluated_at", "uc_model"]
], schema=eval_schema)

(eval_sdf.write.format("delta")
         .mode("append")
         .option("mergeSchema", "true")
         .saveAsTable(eval_runs_fqn))
print(f"Appended {eval_sdf.count()} rows to {eval_runs_fqn}")

# COMMAND ----------
# MAGIC %md ## Pick winner + promote to `@production`
# MAGIC
# MAGIC Winner = highest `secondary_top1_accuracy` on `maverick_holdout` among
# MAGIC the *MLflow-registered* aliases (the GL baseline is a floor, not a
# MAGIC candidate). Ties broken by holdout `secondary_top1_accuracy`.

# COMMAND ----------
candidates = eval_pdf[eval_pdf["model_alias"].isin(present_aliases)]
scores_wide = candidates.pivot_table(
    index="model_alias",
    columns="slice",
    values="secondary_top1_accuracy",
)
print("Leaf-tier accuracy by model × slice:")
print(scores_wide.to_string())

winner = (scores_wide
          .sort_values(by=["maverick_holdout", "holdout"], ascending=False)
          .index[0])
winner_version = client.get_model_version_by_alias(uc_model, winner).version
client.set_registered_model_alias(uc_model, "production", winner_version)
print(f"Promoted {uc_model} v{winner_version} (was @{winner}) → @production")

# Floor check — if the winner doesn't beat the GL baseline by ≥ 10 pp on the
# maverick slice's leaf accuracy, that's a demo-quality red flag (still ship,
# but yell about it in the logs).
gl_row = eval_pdf[(eval_pdf["model_alias"] == "gl_account_baseline")
                  & (eval_pdf["slice"] == "maverick_holdout")].iloc[0]
winner_row = eval_pdf[(eval_pdf["model_alias"] == winner)
                      & (eval_pdf["slice"] == "maverick_holdout")].iloc[0]
margin_pp = (winner_row["secondary_top1_accuracy"] - gl_row["secondary_top1_accuracy"]) * 100
print(f"Winner beats GL baseline on maverick slice by {margin_pp:+.1f} pp (leaf tier)")
if margin_pp < 10:
    print("⚠  Margin < 10 pp — model isn't beating the deterministic GL lookup convincingly.")

# COMMAND ----------
# MAGIC %md ## Per-category breakdown for the winning model on the maverick slice

# COMMAND ----------
from sklearn.metrics import classification_report

model_uri = f"models:/{uc_model}@{winner}"
winner_model = mlflow.pyfunc.load_model(model_uri)
X = maverick_pdf[FEATURE_COLS]
y_leaf = maverick_pdf["label"].astype(str).values
y_parent = maverick_pdf["label_primary"].astype(str).values
preds = pd.DataFrame(winner_model.predict(X))

print("\n--- LEAF-tier classification report (maverick slice) ---")
print(classification_report(
    y_leaf, preds["predicted_secondary_category"].astype(str).values,
    zero_division=0, digits=3,
))

print("\n--- PARENT-tier classification report (maverick slice) ---")
print(classification_report(
    y_parent, preds["predicted_primary_category"].astype(str).values,
    zero_division=0, digits=3,
))
