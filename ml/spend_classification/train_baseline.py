# Databricks notebook source
# MAGIC %md
# MAGIC # Spend classification — TF-IDF + LightGBM baseline
# MAGIC
# MAGIC Reads `<catalog>.ml.spend_clf_train`, trains a multi-class LightGBM
# MAGIC classifier on a sklearn `Pipeline` (TF-IDF on `line_description`,
# MAGIC OneHotEncoder on categorical, passthrough on numeric), MLflow autologs
# MAGIC the run, and registers the model to UC at `<catalog>.ml.spend_classifier`
# MAGIC with alias `@challenger`.
# MAGIC
# MAGIC Target: ≥ 85% top-1 holdout accuracy. See `ml/README.md` § 3 — Baseline.

# COMMAND ----------
dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema_ml", "")
dbutils.widgets.text("model_name", "spend_classifier")
dbutils.widgets.text("model_alias", "challenger")

catalog = dbutils.widgets.get("catalog")
schema_ml = dbutils.widgets.get("schema_ml")
model_name = dbutils.widgets.get("model_name")
model_alias = dbutils.widgets.get("model_alias")

uc_model = f"{catalog}.{schema_ml}.{model_name}"
print(f"Source: {catalog}.{schema_ml}.spend_clf_train")
print(f"Target model: {uc_model}@{model_alias}")

# COMMAND ----------
# MAGIC %md ## Load training data

# COMMAND ----------
# TODO: implementation
# import pandas as pd
# train_pdf = spark.table(f"{catalog}.{schema_ml}.spend_clf_train").toPandas()
#
# TEXT_COL = "line_description"
# CAT_COLS = ["supplier_id", "segment_code", "payment_terms", "currency",
#             "supplier_region", "gl_account", "direct_indirect",
#             "addressability", "category_primary_hint"]
# NUM_COLS = ["log_amount", "log_quantity", "log_unit_price",
#             "supplier_maverick_propensity"]
#
# X = train_pdf[[TEXT_COL] + CAT_COLS + NUM_COLS]
# y = train_pdf["label"]

print("TODO: load training pdf")

# COMMAND ----------
# MAGIC %md ## Pipeline — TF-IDF + One-Hot + LightGBM

# COMMAND ----------
# TODO: implementation
# from sklearn.compose import ColumnTransformer
# from sklearn.feature_extraction.text import TfidfVectorizer
# from sklearn.pipeline import Pipeline
# from sklearn.preprocessing import OneHotEncoder
# from lightgbm import LGBMClassifier
#
# preproc = ColumnTransformer([
#     ("text", TfidfVectorizer(ngram_range=(1, 2), max_features=50_000,
#                              lowercase=True, sublinear_tf=True), TEXT_COL),
#     ("cat",  OneHotEncoder(handle_unknown="ignore", min_frequency=10), CAT_COLS),
#     ("num",  "passthrough", NUM_COLS),
# ])
#
# clf = LGBMClassifier(
#     objective="multiclass",
#     num_class=y.nunique(),
#     n_estimators=500,
#     max_depth=7,
#     learning_rate=0.05,
#     class_weight="balanced",
#     random_state=42,
#     n_jobs=-1,
# )
#
# pipe = Pipeline([("preproc", preproc), ("clf", clf)])

print("TODO: build pipeline")

# COMMAND ----------
# MAGIC %md ## Train + log to MLflow + register to UC

# COMMAND ----------
# TODO: implementation
# import mlflow
# mlflow.set_registry_uri("databricks-uc")
# mlflow.sklearn.autolog(log_input_examples=True, log_model_signatures=True)
#
# with mlflow.start_run(run_name="spend_clf_baseline_lgbm"):
#     pipe.fit(X, y)
#     signature = mlflow.models.infer_signature(X.head(100), pipe.predict(X.head(100)))
#     mlflow.sklearn.log_model(
#         pipe, artifact_path="model",
#         registered_model_name=uc_model,
#         signature=signature,
#         input_example=X.head(5),
#     )
#
# # Set the @challenger alias on the latest registered version
# from mlflow.tracking import MlflowClient
# client = MlflowClient(registry_uri="databricks-uc")
# latest = max(client.search_model_versions(f"name='{uc_model}'"), key=lambda v: int(v.version))
# client.set_registered_model_alias(uc_model, model_alias, latest.version)
# print(f"Registered {uc_model} v{latest.version} → @{model_alias}")

print("TODO: train + register")
