# Databricks notebook source
# MAGIC %md
# MAGIC # Spend classification — batch inference → `ml.invoice_classifications`
# MAGIC
# MAGIC Loads `<catalog>.ml.spend_classifier@production`, scores every row in
# MAGIC `<catalog>.gold.fact_invoices`, and MERGEs predictions into
# MAGIC `<catalog>.ml.invoice_classifications`. `silver.invoice_classification`
# MAGIC reads from that table; `gold.fact_invoices` LEFT-joins through it.
# MAGIC
# MAGIC The pyfunc model (logged by `train_baseline.py`) emits all four target
# MAGIC columns in one shot — `predicted_secondary_category`,
# MAGIC `predicted_primary_category`, `secondary_confidence`,
# MAGIC `primary_confidence` — because the leaf→parent taxonomy is baked into
# MAGIC the model artifact. No taxonomy join is needed here.
# MAGIC
# MAGIC Idempotent — MERGE keyed on `invoice_line_id` overwrites prior
# MAGIC predictions on re-run. Safe to schedule after every model refresh.

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
model_uri = f"models:/{uc_model}@{model_alias}"
target_fqn = f"`{catalog}`.`{schema_ml}`.invoice_classifications"
source_fqn = f"`{catalog}`.`{schema_gold}`.fact_invoices"
print(f"Scoring {source_fqn} with {model_uri}")
print(f"Writing predictions to {target_fqn}")

# COMMAND ----------
# MAGIC %md ## Load production model + resolve version

# COMMAND ----------
import mlflow
from mlflow.tracking import MlflowClient

mlflow.set_registry_uri("databricks-uc")
client = MlflowClient(registry_uri="databricks-uc")
production_version = client.get_model_version_by_alias(uc_model, model_alias).version
model_version_str = f"{uc_model}/v{production_version}"
print(f"Resolved {uc_model}@{model_alias} → v{production_version}")

# COMMAND ----------
# MAGIC %md ## Project feature columns from `gold.fact_invoices`
# MAGIC
# MAGIC The model trained on the schema written by `prepare_features.py`. The
# MAGIC same feature columns must be present here (with the same log-transforms
# MAGIC applied to amount / quantity / unit_price). `category_primary_hint` is
# MAGIC sourced from `dim_supplier.category_primary` at training time; we join
# MAGIC it here too so feature parity holds.

# COMMAND ----------
from pyspark.sql import functions as F

source_sdf = spark.sql(f"""
    SELECT
      fi.invoice_line_id,
      fi.line_description,
      fi.supplier_id,
      fi.segment_code,
      fi.payment_terms,
      fi.currency,
      fi.supplier_region,
      fi.gl_account,
      fi.direct_indirect,
      fi.addressability,
      LN(1 + GREATEST(CAST(fi.amount     AS DOUBLE), 0.0)) AS log_amount,
      LN(1 + GREATEST(CAST(fi.quantity   AS DOUBLE), 0.0)) AS log_quantity,
      LN(1 + GREATEST(CAST(fi.unit_price AS DOUBLE), 0.0)) AS log_unit_price,
      COALESCE(CAST(fi.supplier_maverick_propensity AS DOUBLE), 0.0)
                                                          AS supplier_maverick_propensity,
      COALESCE(ds.category_primary, '__NA__')             AS category_primary_hint
    FROM `{catalog}`.`{schema_gold}`.fact_invoices fi
    LEFT JOIN `{catalog}`.`{schema_gold}`.dim_supplier ds USING (supplier_id)
""")

# Defensive: replace null categoricals with the same sentinel the training pipeline saw.
CAT_COLS = ["supplier_id", "segment_code", "payment_terms", "currency",
            "supplier_region", "gl_account", "direct_indirect",
            "addressability", "category_primary_hint"]
TEXT_COL = "line_description"
NUM_COLS = ["log_amount", "log_quantity", "log_unit_price",
            "supplier_maverick_propensity"]
FEATURE_COLS = [TEXT_COL] + CAT_COLS + NUM_COLS

for c in CAT_COLS:
    source_sdf = source_sdf.withColumn(c, F.coalesce(F.col(c).cast("string"), F.lit("__NA__")))
source_sdf = source_sdf.withColumn(TEXT_COL, F.coalesce(F.col(TEXT_COL), F.lit("")))

n_source = source_sdf.count()
print(f"Source rows to score: {n_source:,}")
assert n_source > 0, f"No rows in {source_fqn} — run the lakehouse pipeline first."

# COMMAND ----------
# MAGIC %md ## Score via `mlflow.pyfunc.spark_udf`
# MAGIC
# MAGIC The pyfunc returns a 4-column DataFrame; we declare the matching struct
# MAGIC result_type so Spark surfaces it as nested fields we can flatten.

# COMMAND ----------
pred_struct = (
    "struct<"
    "predicted_secondary_category:string,"
    "predicted_primary_category:string,"
    "secondary_confidence:double,"
    "primary_confidence:double"
    ">"
)
predict_udf = mlflow.pyfunc.spark_udf(spark, model_uri, result_type=pred_struct)

scored = (
    source_sdf
    .withColumn("pred", predict_udf(*[F.col(c) for c in FEATURE_COLS]))
    .select(
        "invoice_line_id",
        F.col("pred.predicted_secondary_category").alias("predicted_secondary_category"),
        F.col("pred.predicted_primary_category").alias("predicted_primary_category"),
        F.col("pred.secondary_confidence").alias("secondary_confidence"),
        F.col("pred.primary_confidence").alias("primary_confidence"),
    )
    .withColumn("model_version", F.lit(model_version_str))
    .withColumn("scored_at", F.current_timestamp())
)

# Materialize so the MERGE doesn't re-run the spark_udf on every read
scored.cache()
n_scored = scored.count()
print(f"Scored {n_scored:,} invoice lines")

# COMMAND ----------
# MAGIC %md ## MERGE into `<catalog>.ml.invoice_classifications`

# COMMAND ----------
scored.createOrReplaceTempView("scored_v")

spark.sql(f"""
  MERGE INTO {target_fqn} AS tgt
  USING scored_v AS src
    ON tgt.invoice_line_id = src.invoice_line_id
  WHEN MATCHED THEN UPDATE SET
    tgt.predicted_primary_category   = src.predicted_primary_category,
    tgt.predicted_secondary_category = src.predicted_secondary_category,
    tgt.primary_confidence           = src.primary_confidence,
    tgt.secondary_confidence         = src.secondary_confidence,
    tgt.model_version                = src.model_version,
    tgt.scored_at                    = src.scored_at
  WHEN NOT MATCHED THEN INSERT (
    invoice_line_id, predicted_primary_category, predicted_secondary_category,
    primary_confidence, secondary_confidence, model_version, scored_at
  ) VALUES (
    src.invoice_line_id, src.predicted_primary_category, src.predicted_secondary_category,
    src.primary_confidence, src.secondary_confidence, src.model_version, src.scored_at
  )
""")
print(f"MERGE complete into {target_fqn}")

# COMMAND ----------
# MAGIC %md ## Post-merge sanity stats

# COMMAND ----------
print("--- Coverage + confidence distribution ---")
spark.sql(f"""
    SELECT
      COUNT(*)                                         AS total_predictions,
      ROUND(AVG(secondary_confidence), 4)              AS mean_leaf_confidence,
      ROUND(percentile_approx(secondary_confidence, 0.10), 4) AS p10_leaf_confidence,
      ROUND(percentile_approx(secondary_confidence, 0.90), 4) AS p90_leaf_confidence,
      ROUND(AVG(primary_confidence), 4)                AS mean_parent_confidence,
      ROUND(percentile_approx(primary_confidence, 0.10), 4)   AS p10_parent_confidence,
      ROUND(percentile_approx(primary_confidence, 0.90), 4)   AS p90_parent_confidence
    FROM {target_fqn}
""").show(truncate=False)

print("--- Predictions per parent category (top 10) ---")
spark.sql(f"""
    SELECT
      predicted_primary_category,
      COUNT(*)                              AS n_predictions,
      ROUND(AVG(primary_confidence), 4)     AS avg_confidence
    FROM {target_fqn}
    GROUP BY predicted_primary_category
    ORDER BY n_predictions DESC
    LIMIT 10
""").show(truncate=False)

# Tie back to the source — every invoice line should now have a prediction.
print("--- Coverage of fact_invoices ---")
spark.sql(f"""
    SELECT
      COUNT(*) AS fact_invoices_rows,
      SUM(CASE WHEN c.invoice_line_id IS NOT NULL THEN 1 ELSE 0 END) AS rows_with_prediction,
      ROUND(100.0 * SUM(CASE WHEN c.invoice_line_id IS NOT NULL THEN 1 ELSE 0 END) / COUNT(*), 2)
                                                                AS coverage_pct
    FROM {source_fqn} fi
    LEFT JOIN {target_fqn} c
      ON fi.invoice_line_id = c.invoice_line_id
""").show(truncate=False)
