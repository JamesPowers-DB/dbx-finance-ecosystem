# Databricks notebook source
# MAGIC %md
# MAGIC # Spend classification — TF-IDF + LightGBM baseline (2-tier output)
# MAGIC
# MAGIC Reads `<catalog>.ml.spend_clf_train`, trains a multi-class LightGBM
# MAGIC classifier on a sklearn `Pipeline`, then wraps the trained estimator
# MAGIC in a `mlflow.pyfunc.PythonModel` (`SpendClassifierWithTaxonomy`) that
# MAGIC emits the 2-tier prediction surface:
# MAGIC
# MAGIC - `predicted_secondary_category` (leaf)
# MAGIC - `predicted_primary_category` (parent — looked up via leaf→parent map embedded in the wrapper)
# MAGIC - `secondary_confidence` (max softmax prob over leaves)
# MAGIC - `primary_confidence` (sum of softmax probs over all leaves under the predicted parent)
# MAGIC
# MAGIC The leaf→parent map is sourced from `<catalog>.gold.dim_spend_category`
# MAGIC at training time and baked into the model so inference is self-contained
# MAGIC (no taxonomy join needed at score time).
# MAGIC
# MAGIC Registers the wrapped model to UC at `<catalog>.ml.spend_classifier` with
# MAGIC alias `@challenger`. `evaluate.py` promotes the winner to `@production`.
# MAGIC
# MAGIC Target: ≥ 85% leaf top-1 holdout accuracy, ≥ 95% parent top-1.

# COMMAND ----------
dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema", "finance_spend_analytics")
dbutils.widgets.text("model_name", "spend_classifier")
dbutils.widgets.text("model_alias", "challenger")
dbutils.widgets.text("max_train_rows", "0")  # 0 = all rows; set lower for quick smoke tests
dbutils.widgets.text("hpo_trials", "25")         # Optuna trials (0 = skip HPO, use defaults)
dbutils.widgets.text("hpo_sample_rows", "60000") # rows sampled for the HPO search (0 = all)

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
model_name = dbutils.widgets.get("model_name")
model_alias = dbutils.widgets.get("model_alias")
max_train_rows = int(dbutils.widgets.get("max_train_rows"))
hpo_trials = int(dbutils.widgets.get("hpo_trials"))
hpo_sample_rows = int(dbutils.widgets.get("hpo_sample_rows"))

uc_model = f"{catalog}.{schema}.{model_name}"
print(f"Source: {catalog}.{schema}.ml_spend_clf_train")
print(f"Taxonomy: {catalog}.{schema}.gold_dim_spend_category")
print(f"Target model: {uc_model}@{model_alias}")

# COMMAND ----------
# MAGIC %md ## Load training data + taxonomy

# COMMAND ----------
import numpy as np
import pandas as pd
from pyspark.sql import functions as F

TEXT_COL = "line_description"
# LEAKY FEATURES REMOVED: `supplier_id` (one-hot memorizes the near-deterministic
# supplier→category mapping in this synthetic data) and `category_primary_hint`
# (= the supplier's generative category — circular with the label). The model now
# classifies from the line text + defensible tabular signals.
CAT_COLS = ["segment_code", "payment_terms", "currency",
            "supplier_region", "gl_account", "direct_indirect", "addressability"]
NUM_COLS = ["log_amount", "log_quantity", "log_unit_price",
            "supplier_maverick_propensity"]
FEATURE_COLS = [TEXT_COL] + CAT_COLS + NUM_COLS

train_sdf = spark.table(f"`{catalog}`.`{schema}`.ml_spend_clf_train")
if max_train_rows > 0:
    train_sdf = train_sdf.orderBy(F.rand(seed=42)).limit(max_train_rows)
train_pdf = train_sdf.toPandas()

# Fill nulls in categorical columns so OneHotEncoder doesn't crash
for c in CAT_COLS:
    train_pdf[c] = train_pdf[c].fillna("__NA__").astype(str)
train_pdf[TEXT_COL] = train_pdf[TEXT_COL].fillna("").astype(str)
for c in NUM_COLS:
    train_pdf[c] = pd.to_numeric(train_pdf[c], errors="coerce").fillna(0.0)

X = train_pdf[FEATURE_COLS]
y = train_pdf["label"].astype(str)
print(f"Train shape: {X.shape}; {y.nunique()} distinct leaf labels")
print(f"Per-class min count: {y.value_counts().min()}")

# Leaf → Parent map from the UC taxonomy table — single source of truth
taxonomy_pdf = (spark.table(f"`{catalog}`.`{schema}`.gold_dim_spend_category")
                     .select("secondary_code", "primary_code")
                     .toPandas())
leaf_to_parent = dict(zip(taxonomy_pdf["secondary_code"], taxonomy_pdf["primary_code"]))
print(f"Taxonomy: {len(leaf_to_parent)} leaves × {len(set(leaf_to_parent.values()))} parents")

missing_in_taxonomy = set(y.unique()) - set(leaf_to_parent.keys())
assert not missing_in_taxonomy, (
    f"Training labels not in taxonomy: {sorted(missing_in_taxonomy)} — "
    "rebuild dim_spend_category or fix _lib.SPEND_CATEGORY_HIERARCHY."
)

# COMMAND ----------
# MAGIC %md ## Pipeline factory — TF-IDF + One-Hot + LightGBM
# MAGIC
# MAGIC A `build_pipeline(params)` factory so the Optuna search and the final fit
# MAGIC share one construction. The leaky categoricals are already excluded from
# MAGIC `CAT_COLS`, so the model leans on `line_description` + tabular signals.

# COMMAND ----------
from sklearn.compose import ColumnTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from lightgbm import LGBMClassifier

N_CLASSES = int(y.nunique())

DEFAULT_PARAMS = {
    "tfidf_max_features": 20_000, "tfidf_ngram_max": 2, "tfidf_min_df": 3,
    "lgbm_n_estimators": 300, "lgbm_max_depth": 8, "lgbm_num_leaves": 63,
    "lgbm_learning_rate": 0.05, "lgbm_min_child_samples": 20, "lgbm_reg_lambda": 0.0,
    "lgbm_subsample": 1.0, "lgbm_colsample_bytree": 1.0,
}


def build_pipeline(params: dict) -> Pipeline:
    preproc = ColumnTransformer([
        ("text", TfidfVectorizer(
            ngram_range=(1, int(params["tfidf_ngram_max"])),
            max_features=int(params["tfidf_max_features"]),
            lowercase=True, sublinear_tf=True, min_df=int(params["tfidf_min_df"]),
         ), TEXT_COL),
        ("cat",  OneHotEncoder(handle_unknown="ignore", min_frequency=50, sparse_output=True), CAT_COLS),
        ("num",  "passthrough", NUM_COLS),
    ])
    clf = LGBMClassifier(
        objective="multiclass", num_class=N_CLASSES,
        n_estimators=int(params["lgbm_n_estimators"]),
        max_depth=int(params["lgbm_max_depth"]),
        num_leaves=int(params["lgbm_num_leaves"]),
        learning_rate=float(params["lgbm_learning_rate"]),
        min_child_samples=int(params["lgbm_min_child_samples"]),
        reg_lambda=float(params["lgbm_reg_lambda"]),
        subsample=float(params["lgbm_subsample"]),
        colsample_bytree=float(params["lgbm_colsample_bytree"]),
        class_weight="balanced", random_state=42, n_jobs=-1, verbosity=-1,
    )
    return Pipeline([("preproc", preproc), ("clf", clf)])

# COMMAND ----------
# MAGIC %md ## Hyperparameter search (Optuna)
# MAGIC
# MAGIC Maximizes **macro-F1** on a stratified validation split (macro-F1 respects
# MAGIC the class imbalance across the 30 leaves — accuracy would flatter the big
# MAGIC classes). Runs on a row sub-sample for speed; the winner is refit on the full
# MAGIC training set below. Set `hpo_trials=0` to skip and use `DEFAULT_PARAMS`.

# COMMAND ----------
import optuna
from sklearn.model_selection import train_test_split
from sklearn.metrics import f1_score

if hpo_trials > 0:
    if hpo_sample_rows > 0 and len(X) > hpo_sample_rows:
        X_hpo, _, y_hpo, _ = train_test_split(
            X, y, train_size=hpo_sample_rows, stratify=y, random_state=42)
    else:
        X_hpo, y_hpo = X, y
    X_tr, X_val, y_tr, y_val = train_test_split(
        X_hpo, y_hpo, test_size=0.25, stratify=y_hpo, random_state=42)
    print(f"HPO search: {len(X_tr):,} train / {len(X_val):,} val rows over {hpo_trials} trials")

    def objective(trial):
        params = {
            "tfidf_max_features": trial.suggest_categorical("tfidf_max_features", [5_000, 10_000, 20_000]),
            "tfidf_ngram_max":    trial.suggest_int("tfidf_ngram_max", 1, 2),
            "tfidf_min_df":       trial.suggest_int("tfidf_min_df", 2, 5),
            "lgbm_n_estimators":  trial.suggest_int("lgbm_n_estimators", 200, 600, step=100),
            "lgbm_max_depth":     trial.suggest_int("lgbm_max_depth", 4, 12),
            "lgbm_num_leaves":    trial.suggest_int("lgbm_num_leaves", 31, 127),
            "lgbm_learning_rate": trial.suggest_float("lgbm_learning_rate", 0.02, 0.2, log=True),
            "lgbm_min_child_samples": trial.suggest_int("lgbm_min_child_samples", 10, 100),
            "lgbm_reg_lambda":    trial.suggest_float("lgbm_reg_lambda", 1e-3, 10.0, log=True),
            "lgbm_subsample":     trial.suggest_float("lgbm_subsample", 0.6, 1.0),
            "lgbm_colsample_bytree": trial.suggest_float("lgbm_colsample_bytree", 0.6, 1.0),
        }
        p = build_pipeline(params)
        p.fit(X_tr, y_tr)
        return f1_score(y_val, p.predict(X_val), average="macro")

    study = optuna.create_study(direction="maximize",
                                sampler=optuna.samplers.TPESampler(seed=42))
    study.optimize(objective, n_trials=hpo_trials, show_progress_bar=False)
    best_params = {**DEFAULT_PARAMS, **study.best_params}
    best_hpo_f1 = float(study.best_value)
    print(f"Optuna best macro-F1 (val sub-sample): {best_hpo_f1:.4f}")
    print(f"Best params: {study.best_params}")
else:
    best_params = dict(DEFAULT_PARAMS)
    best_hpo_f1 = float("nan")
    print("HPO disabled (hpo_trials=0) — using DEFAULT_PARAMS")

# Final estimator (refit on the full training set in the MLflow run below).
pipe = build_pipeline(best_params)

# COMMAND ----------
# MAGIC %md ## Custom pyfunc wrapper — emits the 2-tier prediction surface
# MAGIC
# MAGIC Wrapping the sklearn estimator in a pyfunc lets us:
# MAGIC 1. Compute parent confidence by summing softmax probabilities under the
# MAGIC    predicted parent — without re-querying the taxonomy at inference time.
# MAGIC 2. Emit a structured prediction (`predicted_primary_category`,
# MAGIC    `predicted_secondary_category`, `primary_confidence`, `secondary_confidence`)
# MAGIC    that `batch_inference.py` can MERGE directly into `ml.invoice_classifications`.
# MAGIC 3. Pin the taxonomy as it existed at training time — if `dim_spend_category`
# MAGIC    changes shape, old model versions still emit deterministic predictions
# MAGIC    over their original taxonomy.

# COMMAND ----------
import mlflow.pyfunc


class SpendClassifierWithTaxonomy(mlflow.pyfunc.PythonModel):
    """Wraps an sklearn estimator with a leaf→parent taxonomy lookup.

    predict() returns a pandas DataFrame with four columns:
      predicted_secondary_category, predicted_primary_category,
      secondary_confidence, primary_confidence.
    """

    def __init__(self, sklearn_model, leaf_to_parent, feature_cols):
        self.sklearn_model = sklearn_model
        self.leaf_to_parent = dict(leaf_to_parent)
        self.feature_cols = list(feature_cols)
        # Ordered leaf codes the model knows (== sklearn_model.classes_)
        self.classes_ = list(sklearn_model.classes_)
        # Ordered parent codes
        self.parents_ = sorted(set(self.leaf_to_parent.values()))
        # For each leaf index, which parent index does it belong to?
        self._parent_idx_by_leaf = np.array([
            self.parents_.index(self.leaf_to_parent[leaf]) for leaf in self.classes_
        ], dtype=np.int64)
        # Membership matrix M shape (n_parents, n_leaves) where M[p, l]=1 if leaf l's parent is p.
        n_parents = len(self.parents_)
        n_leaves = len(self.classes_)
        M = np.zeros((n_parents, n_leaves), dtype=np.float64)
        for l_idx, p_idx in enumerate(self._parent_idx_by_leaf):
            M[p_idx, l_idx] = 1.0
        self._M = M

    def predict(self, context, model_input):
        # Coerce + reorder columns to match training. Tolerate extra columns
        # passed by callers (e.g., invoice_line_id from spark_udf upstream).
        X = pd.DataFrame(model_input)[self.feature_cols].copy()
        for c in [c for c in self.feature_cols if c not in NUM_COLS_RUNTIME]:
            X[c] = X[c].fillna("__NA__").astype(str) if c != TEXT_COL_RUNTIME else X[c].fillna("").astype(str)
        for c in NUM_COLS_RUNTIME:
            X[c] = pd.to_numeric(X[c], errors="coerce").fillna(0.0)

        proba = self.sklearn_model.predict_proba(X)  # (n_rows, n_leaves)
        leaf_idx = proba.argmax(axis=1)
        labels = np.array([self.classes_[i] for i in leaf_idx])
        confidences = proba.max(axis=1).astype(np.float64)
        # Parent prob mass per row
        parent_probs = proba @ self._M.T  # (n_rows, n_parents)
        parent_idx = self._parent_idx_by_leaf[leaf_idx]
        parents = np.array([self.parents_[i] for i in parent_idx])
        parent_confidences = parent_probs[np.arange(len(leaf_idx)), parent_idx].astype(np.float64)

        return pd.DataFrame({
            "predicted_secondary_category": labels,
            "predicted_primary_category":   parents,
            "secondary_confidence":         confidences,
            "primary_confidence":           parent_confidences,
        })


# These globals are picked up by the wrapper's predict() — kept module-level so
# the wrapper class stays small + serializable. (cloudpickle captures globals
# referenced by methods at log time.)
TEXT_COL_RUNTIME = TEXT_COL
NUM_COLS_RUNTIME = NUM_COLS

# COMMAND ----------
# MAGIC %md ## Train + log to MLflow + register to UC

# COMMAND ----------
import mlflow
from mlflow.models import infer_signature
from mlflow.tracking import MlflowClient

mlflow.set_registry_uri("databricks-uc")
# We use mlflow.pyfunc.log_model directly (not autolog) so the registered model
# is the pyfunc wrapper — not the bare sklearn estimator.
mlflow.autolog(disable=True)

with mlflow.start_run(run_name="spend_clf_baseline_lgbm_2tier") as run:
    print("Fitting sklearn pipeline …")
    pipe.fit(X, y)

    # Build the taxonomy-aware wrapper
    wrapper = SpendClassifierWithTaxonomy(pipe, leaf_to_parent, FEATURE_COLS)

    # Quick in-memory smoke test of the wrapper on a small slice
    sample_in = X.head(5)
    sample_out = wrapper.predict(None, sample_in)
    print("Sample predictions:\n", sample_out)

    # Log basic metrics (training accuracy as a sanity check — eval.py is authoritative)
    train_preds = wrapper.predict(None, X.head(20_000) if len(X) > 20_000 else X)
    train_subset = y.iloc[:len(train_preds)].values
    leaf_acc = float((train_preds["predicted_secondary_category"].values == train_subset).mean())
    parent_truth = np.array([leaf_to_parent[l] for l in train_subset])
    parent_acc = float((train_preds["predicted_primary_category"].values == parent_truth).mean())
    mlflow.log_metric("train_leaf_top1_accuracy", leaf_acc)
    mlflow.log_metric("train_parent_top1_accuracy", parent_acc)
    mlflow.log_metric("train_n_rows", float(len(X)))
    mlflow.log_metric("train_n_leaf_classes", float(y.nunique()))
    mlflow.log_metric("train_n_parent_classes", float(len(set(leaf_to_parent.values()))))
    mlflow.log_params(best_params)
    mlflow.log_param("ohe_min_frequency", 50)
    mlflow.log_param("hpo_trials", hpo_trials)
    mlflow.log_param("feature_cols", ",".join(FEATURE_COLS))
    mlflow.log_param("dropped_leaky_features", "supplier_id,category_primary_hint")
    if hpo_trials > 0:
        mlflow.log_metric("hpo_best_val_macro_f1", best_hpo_f1)
    print(f"Training leaf accuracy: {leaf_acc:.4f}; parent accuracy: {parent_acc:.4f}")

    # Signature: input = features, output = the 4-column DataFrame
    signature = infer_signature(sample_in, sample_out)

    mlflow.pyfunc.log_model(
        artifact_path="model",
        python_model=wrapper,
        registered_model_name=uc_model,
        signature=signature,
        input_example=sample_in,
        pip_requirements=[
            "scikit-learn",
            "lightgbm",
            "pandas",
            "numpy",
            "cloudpickle",
        ],
    )
    run_id = run.info.run_id
    print(f"Logged run {run_id} → {uc_model}")

# COMMAND ----------
# MAGIC %md ## Set the @challenger alias on the latest registered version

# COMMAND ----------
client = MlflowClient(registry_uri="databricks-uc")
versions = client.search_model_versions(f"name='{uc_model}'")
latest = max(versions, key=lambda v: int(v.version))
client.set_registered_model_alias(uc_model, model_alias, latest.version)
print(f"Registered {uc_model} v{latest.version} → @{model_alias}")
print(f"Run ID: {run_id}")
