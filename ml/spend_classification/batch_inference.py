# Databricks notebook source
# MAGIC %md
# MAGIC # Spend classification — batch inference → `ml.invoice_classifications`
# MAGIC
# MAGIC Loads `<catalog>.ml.spend_classifier@production`, scores every row in
# MAGIC `<catalog>.gold.fact_invoices`, and MERGEs predictions into
# MAGIC `<catalog>.ml.invoice_classifications`. `silver.invoice_classification`
# MAGIC reads from that table; `gold.fact_invoices` LEFT-joins the silver MV.
# MAGIC The LEFT JOIN pattern means fact_invoices is always queryable — rows
# MAGIC carry NULL predictions until this job has run for the first time.
# MAGIC
# MAGIC Output schema of `ml.invoice_classifications`:
# MAGIC
# MAGIC | Column | Source |
# MAGIC |---|---|
# MAGIC | `invoice_line_id` | join key from gold.fact_invoices |
# MAGIC | `predicted_category` | argmax over the 30-category softmax |
# MAGIC | `classification_confidence` | max softmax probability |
# MAGIC | `model_version` | MLflow model version that produced the row |
# MAGIC | `scored_at` | wall-clock at inference time |
# MAGIC
# MAGIC Idempotent — MERGE keyed on invoice_line_id overwrites prior predictions
# MAGIC on re-run.

# COMMAND ----------
dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema_gold", "")
dbutils.widgets.text("schema_ml", "")
dbutils.widgets.text("model_name", "spend_classifier")
dbutils.widgets.text("model_alias", "production")

catalog = dbutils.widgets.get("catalog")
schema_gold = dbutils.widgets.get("schema_gold")
schema_ml = dbutils.widgets.get("schema_ml")
model_name = dbutils.widgets.get("model_name")
model_alias = dbutils.widgets.get("model_alias")

uc_model = f"{catalog}.{schema_ml}.{model_name}"
print(f"Scoring {catalog}.{schema_gold}.fact_invoices with {uc_model}@{model_alias}")
print(f"Writing predictions to {catalog}.{schema_ml}.invoice_classifications")

# COMMAND ----------
# MAGIC %md ## Load production model + source rows

# COMMAND ----------
# TODO: implementation
# import mlflow
# mlflow.set_registry_uri("databricks-uc")
# model_uri = f"models:/{uc_model}@{model_alias}"
# loaded = mlflow.pyfunc.load_model(model_uri)
# model_version = loaded.metadata.run_id  # or registry version lookup
#
# source = spark.table(f"{catalog}.{schema_gold}.fact_invoices").select(
#     "invoice_line_id", "line_description",
#     "supplier_id", "segment_code",
#     "payment_terms", "currency", "supplier_region",
#     "gl_account", "direct_indirect", "addressability",
#     "amount", "quantity", "unit_price",
#     "supplier_maverick_propensity",
# )
print("TODO: load model + source")

# COMMAND ----------
# MAGIC %md ## Score (Spark batch via mlflow.pyfunc.spark_udf)

# COMMAND ----------
# TODO: implementation
# from pyspark.sql import functions as F
#
# predict_udf = mlflow.pyfunc.spark_udf(spark, model_uri, result_type="struct<label:string,confidence:float>")
#
# # Apply log-transforms to match training preprocessing (see prepare_features.py)
# features = source.withColumns({
#     "log_amount":     F.log1p(F.col("amount")),
#     "log_quantity":   F.log1p(F.col("quantity")),
#     "log_unit_price": F.log1p(F.col("unit_price")),
# })
#
# scored = features.withColumn("pred", predict_udf(*[F.col(c) for c in <feature_cols>])) \
#                  .select(
#                      "invoice_line_id",
#                      F.col("pred.label").alias("predicted_category"),
#                      F.col("pred.confidence").cast("double").alias("classification_confidence"),
#                      F.lit(model_version).alias("model_version"),
#                      F.current_timestamp().alias("scored_at"),
#                  )
print("TODO: score via spark_udf")

# COMMAND ----------
# MAGIC %md ## MERGE into `<catalog>.ml.invoice_classifications`
# MAGIC
# MAGIC The table is created (empty) by the data-generation seed step
# MAGIC (`01_period_anchors_seed.py`). Keyed on `invoice_line_id` so re-runs
# MAGIC after retraining cleanly overwrite prior predictions.

# COMMAND ----------
# TODO: implementation
# scored.createOrReplaceTempView("scored_v")
# spark.sql(f"""
#   MERGE INTO `{catalog}`.`{schema_ml}`.invoice_classifications AS tgt
#   USING scored_v AS src
#     ON tgt.invoice_line_id = src.invoice_line_id
#   WHEN MATCHED THEN UPDATE SET
#     tgt.predicted_category        = src.predicted_category,
#     tgt.classification_confidence = src.classification_confidence,
#     tgt.model_version             = src.model_version,
#     tgt.scored_at                 = src.scored_at
#   WHEN NOT MATCHED THEN INSERT *
# """)
print("TODO: MERGE into ml.invoice_classifications")

# COMMAND ----------
# MAGIC %md ## Post-merge sanity
# MAGIC
# MAGIC - Coverage: % of fact_invoices rows that now have a prediction.
# MAGIC - Confidence distribution: mean / p10 / p90.
# MAGIC - Per-segment classification rate.

# COMMAND ----------
# TODO: print summary stats
print("TODO: print coverage + confidence stats")
