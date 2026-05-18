# Databricks notebook source
# MAGIC %md
# MAGIC # Spend classification — feature engineering
# MAGIC
# MAGIC Reads `gold.fact_invoices` joined with `dim_supplier`. Produces three Delta
# MAGIC tables in `<catalog>.ml`:
# MAGIC
# MAGIC | Table | Purpose |
# MAGIC |---|---|
# MAGIC | `spend_clf_train` | Stratified 80% (per category) — training set |
# MAGIC | `spend_clf_holdout` | Stratified 20% (per category, **excluding** maverick suppliers) — primary eval slice |
# MAGIC | `spend_clf_maverick_holdout` | All POs from suppliers with `maverick_propensity > 0.15` — hard-case eval |
# MAGIC
# MAGIC Deterministic split (seeded). Re-running overwrites the three tables.
# MAGIC See `ml/README.md` § 4 for the full feature list and rationale.

# COMMAND ----------
from pyspark.sql import functions as F

dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema_gold", "")
dbutils.widgets.text("schema_ml", "")
dbutils.widgets.text("maverick_threshold", "0.15")
dbutils.widgets.text("test_size", "0.20")
dbutils.widgets.text("random_seed", "42")

catalog = dbutils.widgets.get("catalog")
schema_gold = dbutils.widgets.get("schema_gold")
schema_ml = dbutils.widgets.get("schema_ml")
maverick_threshold = float(dbutils.widgets.get("maverick_threshold"))
test_size = float(dbutils.widgets.get("test_size"))
random_seed = int(dbutils.widgets.get("random_seed"))

assert catalog and schema_gold and schema_ml, "catalog / schema_gold / schema_ml must be set"

print(f"Source: {catalog}.{schema_gold}.fact_invoices  +  {catalog}.{schema_gold}.dim_supplier")
print(f"Target: {catalog}.{schema_ml}.spend_clf_*")
print(f"Maverick threshold: {maverick_threshold}  |  test_size: {test_size}  |  seed: {random_seed}")

# COMMAND ----------
# MAGIC %md ## Ensure target schema exists

# COMMAND ----------
spark.sql(f"CREATE SCHEMA IF NOT EXISTS `{catalog}`.`{schema_ml}`")

# COMMAND ----------
# MAGIC %md ## Project features
# MAGIC
# MAGIC One row per invoice line with model-ready columns:
# MAGIC - **Text**: `line_description`
# MAGIC - **Categorical**: `supplier_id`, `segment_code`, `payment_terms`, `currency`, `supplier_region`, `gl_account`, `direct_indirect`, `addressability`, `category_primary_hint`
# MAGIC - **Numeric (log-transformed)**: `log_amount`, `log_quantity`, `log_unit_price`
# MAGIC - **Derived**: `supplier_maverick_propensity`, `is_maverick_supplier`
# MAGIC - **Label**: `label` ← `true_spend_category`

# COMMAND ----------
features = spark.sql(f"""
  SELECT
    fi.invoice_line_id,
    fi.invoice_number,
    fi.line_number,
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
    COALESCE(CAST(fi.supplier_maverick_propensity AS DOUBLE), 0.0) AS supplier_maverick_propensity,
    ds.category_primary                            AS category_primary_hint,
    fi.true_spend_category                         AS label,
    CASE
      WHEN COALESCE(CAST(fi.supplier_maverick_propensity AS DOUBLE), 0.0) > {maverick_threshold} THEN TRUE
      ELSE FALSE
    END AS is_maverick_supplier
  FROM `{catalog}`.`{schema_gold}`.fact_invoices fi
  LEFT JOIN `{catalog}`.`{schema_gold}`.dim_supplier ds USING (supplier_id)
  WHERE fi.true_spend_category IS NOT NULL
""")

total_rows = features.count()
print(f"Projected {total_rows:,} feature rows from fact_invoices")

# COMMAND ----------
# MAGIC %md ## Split — maverick first, then stratified 80/20 on the remainder

# COMMAND ----------
maverick = features.filter(F.col("is_maverick_supplier"))
regular  = features.filter(~F.col("is_maverick_supplier"))

# Stratified sample by label using sampleBy. Fractions dict: every label → train_frac.
unique_labels = [r.label for r in regular.select("label").distinct().collect()]
train_frac = 1.0 - test_size
fractions = {label: train_frac for label in unique_labels}

train = regular.sampleBy("label", fractions, seed=random_seed).cache()

# Holdout = regular minus train, via left_anti on the natural key (invoice_line_id).
holdout = regular.join(
    train.select("invoice_line_id"),
    on=["invoice_line_id"],
    how="left_anti",
)

train_n   = train.count()
holdout_n = holdout.count()
maverick_n = maverick.count()
print(f"Train:    {train_n:,} rows")
print(f"Holdout:  {holdout_n:,} rows  (target ≈ {int(total_rows * test_size * (1 - maverick.count() / max(total_rows, 1))):,})")
print(f"Maverick: {maverick_n:,} rows")
print(f"Sum check: {train_n + holdout_n + maverick_n:,}  vs total {total_rows:,}  "
      f"(drift = {(train_n + holdout_n + maverick_n) - total_rows})")

# COMMAND ----------
# MAGIC %md ## Write three Delta tables (overwrite — idempotent)

# COMMAND ----------
for table_name, df in [
    ("spend_clf_train", train),
    ("spend_clf_holdout", holdout),
    ("spend_clf_maverick_holdout", maverick),
]:
    fqn = f"`{catalog}`.`{schema_ml}`.{table_name}"
    (df.write.format("delta")
       .mode("overwrite")
       .option("overwriteSchema", "true")
       .saveAsTable(fqn))
    print(f"Wrote {fqn}: {spark.table(fqn).count():,} rows")

# COMMAND ----------
# MAGIC %md ## Sanity checks
# MAGIC
# MAGIC - Every label appears in train AND holdout (no class is missing from either).
# MAGIC - Per-class counts look reasonable in train (no single class < 50 rows).
# MAGIC - Maverick holdout is non-trivially sized.

# COMMAND ----------
train_labels   = {r.label for r in spark.table(f"`{catalog}`.`{schema_ml}`.spend_clf_train").select("label").distinct().collect()}
holdout_labels = {r.label for r in spark.table(f"`{catalog}`.`{schema_ml}`.spend_clf_holdout").select("label").distinct().collect()}

missing_from_train = holdout_labels - train_labels
missing_from_holdout = train_labels - holdout_labels
if missing_from_train:
    print(f"⚠️  Labels in holdout but not train: {sorted(missing_from_train)}")
if missing_from_holdout:
    print(f"⚠️  Labels in train but not holdout: {sorted(missing_from_holdout)}")
if not missing_from_train and not missing_from_holdout:
    print(f"✓ All {len(train_labels)} labels appear in both train and holdout")

print("\nPer-class train counts (smallest 5):")
spark.table(f"`{catalog}`.`{schema_ml}`.spend_clf_train") \
     .groupBy("label").count() \
     .orderBy("count").limit(5).show(truncate=False)

print("\nPer-class train counts (largest 5):")
spark.table(f"`{catalog}`.`{schema_ml}`.spend_clf_train") \
     .groupBy("label").count() \
     .orderBy(F.col("count").desc()).limit(5).show(truncate=False)

if maverick_n < 100:
    print(f"\n⚠️  Maverick holdout is small ({maverick_n} rows). "
          f"Consider lowering maverick_threshold (currently {maverick_threshold}).")
else:
    print(f"\n✓ Maverick holdout has {maverick_n:,} rows — enough for meaningful eval")
