# Databricks notebook source
# MAGIC %md
# MAGIC # Spend classification — evaluation across three slices
# MAGIC
# MAGIC Compares all registered model aliases (`@challenger`, `@challenger_embedding`,
# MAGIC plus a synthetic `@matgroup_baseline` lookup) on three eval slices:
# MAGIC
# MAGIC | Slice | Source | Purpose |
# MAGIC |---|---|---|
# MAGIC | Holdout | `<catalog>.ml.spend_clf_holdout` | Primary accuracy metric |
# MAGIC | Maverick holdout | `<catalog>.ml.spend_clf_maverick_holdout` | The hard-case slice — most important for sourcing |
# MAGIC | GL-account baseline | computed on holdout | Sanity floor — model must beat by ≥ 10 pp |
# MAGIC
# MAGIC Writes a comparison table to `<catalog>.ml.spend_clf_eval_runs` and
# MAGIC promotes the winner (highest **maverick-slice accuracy**, then overall
# MAGIC top-1) to alias `@production`.
# MAGIC
# MAGIC See `ml/README.md` § 4 — Evaluation.

# COMMAND ----------
dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema_ml", "")
dbutils.widgets.text("model_name", "spend_classifier")

catalog = dbutils.widgets.get("catalog")
schema_ml = dbutils.widgets.get("schema_ml")
model_name = dbutils.widgets.get("model_name")

uc_model = f"{catalog}.{schema_ml}.{model_name}"
print(f"Evaluating aliases of {uc_model}")

# COMMAND ----------
# MAGIC %md ## Build the MATGROUP-only baseline

# COMMAND ----------
# TODO: implementation
# `material_group_code → most-common true_spend_category` lookup built from
# the training set. Wrap as a pyfunc model so we can call it through the
# same evaluation harness as the real models.
print("TODO: build matgroup baseline")

# COMMAND ----------
# MAGIC %md ## Load eval slices

# COMMAND ----------
# TODO: implementation
# holdout = spark.table(f"{catalog}.{schema_ml}.spend_clf_holdout").toPandas()
# maverick = spark.table(f"{catalog}.{schema_ml}.spend_clf_maverick_holdout").toPandas()
print("TODO: load holdouts")

# COMMAND ----------
# MAGIC %md ## Score every model × every slice

# COMMAND ----------
# TODO: implementation
# from mlflow.tracking import MlflowClient
# from sklearn.metrics import accuracy_score, top_k_accuracy_score, f1_score, classification_report
#
# client = MlflowClient(registry_uri="databricks-uc")
# aliases_to_eval = ["challenger", "challenger_embedding"]  # plus the synthetic matgroup baseline
#
# results = []
# for alias in aliases_to_eval:
#     model = mlflow.pyfunc.load_model(f"models:/{uc_model}@{alias}")
#     for slice_name, df in [("holdout", holdout), ("maverick_holdout", maverick)]:
#         X, y = df.drop(columns=["label"]), df["label"]
#         y_pred = model.predict(X)
#         # also get y_proba for top-k + calibration if the model exposes it
#         results.append({
#             "model_alias": alias,
#             "slice": slice_name,
#             "top1_accuracy": accuracy_score(y, y_pred),
#             "macro_f1": f1_score(y, y_pred, average="macro"),
#             "n_rows": len(y),
#         })

print("TODO: score models")

# COMMAND ----------
# MAGIC %md ## Comparison table + winner selection
# MAGIC
# MAGIC Persist results so a dashboard can show champion-vs-challenger trends.
# MAGIC Winner = highest `maverick_holdout` top-1, ties broken by overall top-1.

# COMMAND ----------
# TODO: implementation
# eval_pdf = pd.DataFrame(results)
# eval_sdf = spark.createDataFrame(eval_pdf)
# (eval_sdf.write.format("delta")
#          .mode("append")
#          .saveAsTable(f"{catalog}.{schema_ml}.spend_clf_eval_runs"))
#
# # Pick winner
# scores = eval_pdf.pivot_table(index="model_alias", columns="slice", values="top1_accuracy")
# winner = scores.sort_values(by=["maverick_holdout", "holdout"], ascending=False).index[0]
#
# # Promote
# winner_version = client.get_model_version_by_alias(uc_model, winner).version
# client.set_registered_model_alias(uc_model, "production", winner_version)
# print(f"Promoted {uc_model} v{winner_version} (was @{winner}) → @production")

print("TODO: rank + promote winner to @production")

# COMMAND ----------
# MAGIC %md ## Per-category report (the section that goes in the demo deck)
# MAGIC
# MAGIC For the production model on the maverick slice, show:
# MAGIC - Confusion matrix (which categories are confused most)
# MAGIC - Per-category precision / recall / F1
# MAGIC - Top 10 worst-performing categories (good story for "model finds the hard cases")

# COMMAND ----------
# TODO: classification_report + confusion matrix visualizations
print("TODO: per-category report")
