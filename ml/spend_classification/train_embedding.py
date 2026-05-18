# Databricks notebook source
# MAGIC %md
# MAGIC # Spend classification — Foundation Model embedding variant (optional)
# MAGIC
# MAGIC Alternative architecture to the LightGBM baseline:
# MAGIC
# MAGIC 1. Embed `line_description` via the Databricks Foundation Model API
# MAGIC    (`databricks-bge-large-en`, 1024-dim) — cached in
# MAGIC    `<catalog>.ml.spend_clf_embeddings_cache` keyed by sha256 of the description.
# MAGIC 2. Concatenate `[embedding ; tabular_features]`.
# MAGIC 3. Train a small classifier head (logistic regression or 2-layer MLP).
# MAGIC 4. Register as `@challenger_embedding` for comparison vs. the TF-IDF baseline.
# MAGIC
# MAGIC See `ml/README.md` § 3 — Variant.

# COMMAND ----------
dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema_ml", "")
dbutils.widgets.text("model_name", "spend_classifier")
dbutils.widgets.text("model_alias", "challenger_embedding")
dbutils.widgets.text("embedding_endpoint", "databricks-bge-large-en")
dbutils.widgets.text("batch_size", "1000")

catalog = dbutils.widgets.get("catalog")
schema_ml = dbutils.widgets.get("schema_ml")
model_name = dbutils.widgets.get("model_name")
model_alias = dbutils.widgets.get("model_alias")
embedding_endpoint = dbutils.widgets.get("embedding_endpoint")
batch_size = int(dbutils.widgets.get("batch_size"))

print(f"Embedding endpoint: {embedding_endpoint}")
print(f"Target model: {catalog}.{schema_ml}.{model_name}@{model_alias}")

# COMMAND ----------
# MAGIC %md ## Step 1 — Embed `line_description` (with cache)

# COMMAND ----------
# TODO: implementation
# import hashlib
# from mlflow.deployments import get_deploy_client
#
# def sha(s: str) -> str:
#     return hashlib.sha256(s.encode("utf-8")).hexdigest()
#
# # Pull descriptions, dedup, check cache, embed only the new ones.
# train = spark.table(f"{catalog}.{schema_ml}.spend_clf_train")
# unique_desc = (train.select("line_description").distinct()
#                     .withColumn("desc_hash", F.udf(sha)("line_description")))
#
# cache_table = f"{catalog}.{schema_ml}.spend_clf_embeddings_cache"
# # ... check existence, diff cached vs needed, embed in batches via get_deploy_client().predict()

print("TODO: embed line_description and cache")

# COMMAND ----------
# MAGIC %md ## Step 2 — Build feature matrix (embedding + tabular)

# COMMAND ----------
# TODO: implementation
# Join embedding cache back to training rows by desc_hash.
# Result: a wide pandas DataFrame with 1024 embedding cols + tabular features.
print("TODO: assemble features")

# COMMAND ----------
# MAGIC %md ## Step 3 — Train classifier head

# COMMAND ----------
# TODO: implementation
# Start with logistic regression as a clean baseline-on-top-of-embeddings.
# Try a small MLP (1 hidden layer, 256 units, dropout 0.2) if logistic is weak.
# Log to MLflow alongside baseline run.
print("TODO: train + log classifier head")

# COMMAND ----------
# MAGIC %md ## Step 4 — Register to UC with @challenger_embedding alias

# COMMAND ----------
# TODO: implementation — mirrors the registration in train_baseline.py
print("TODO: register model")
