# Databricks notebook source
# MAGIC %md
# MAGIC # Spend classification — sourcing-strategy gold view
# MAGIC
# MAGIC Creates `<catalog>.gold.vw_sourcing_strategy` — the *value-delivered*
# MAGIC layer that sourcing organizations consume. Built on top of the
# MAGIC ML-classified `fact_invoices` (after `batch_inference.py` populates
# MAGIC `<catalog>.ml.invoice_classifications`, which `fact_invoices` LEFT-joins
# MAGIC via `silver.invoice_classification` → `predicted_category` /
# MAGIC `classification_confidence`).
# MAGIC
# MAGIC Four analytics surfaced by the view:
# MAGIC
# MAGIC 1. **Category concentration** — spend by category × segment × supplier-share, with a Herfindahl index for monopsony risk.
# MAGIC 2. **Maverick spend per category** — total $ where the supplier's `category_primary` doesn't match the predicted category.
# MAGIC 3. **Off-contract category spend** — joined with `silver.contract_inbound` to flag spend not covered by an active inbound contract.
# MAGIC 4. **Tail spend per segment** — categories where one segment buys < 5% of company total — candidates for consolidation.
# MAGIC
# MAGIC See `ml/README.md` § 4 — Sourcing strategy view.

# COMMAND ----------
dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema_gold", "")
dbutils.widgets.text("schema_silver", "")

catalog = dbutils.widgets.get("catalog")
schema_gold = dbutils.widgets.get("schema_gold")
schema_silver = dbutils.widgets.get("schema_silver")

print(f"Building {catalog}.{schema_gold}.vw_sourcing_strategy")

# COMMAND ----------
# MAGIC %md ## The view

# COMMAND ----------
# TODO: implementation
# spark.sql(f"""
# CREATE OR REPLACE VIEW `{catalog}`.`{schema_gold}`.vw_sourcing_strategy AS
# WITH spend AS (
#   SELECT
#     fi.fiscal_year, fi.fiscal_quarter, fi.segment_code,
#     fi.predicted_category,
#     fi.classification_confidence,
#     fi.supplier_id, fi.supplier_name,
#     fi.addressability,
#     fi.direct_indirect,
#     fi.amount,
#     ds.category_primary AS supplier_primary_category
#   FROM `{catalog}`.`{schema_gold}`.fact_invoices fi
#   LEFT JOIN `{catalog}`.`{schema_gold}`.dim_supplier ds USING (supplier_id)
#   WHERE fi.predicted_category IS NOT NULL
#     AND fi.addressability = 'Addressable'   -- exclude regulated suppliers
# ),
# category_supplier_share AS (
#   SELECT fiscal_year, fiscal_quarter, segment_code, predicted_category, supplier_id,
#          SUM(amount) AS supplier_spend_in_category,
#          SUM(SUM(amount)) OVER (
#            PARTITION BY fiscal_year, fiscal_quarter, segment_code, predicted_category
#          ) AS category_total,
#          POW(SUM(amount) / NULLIF(SUM(SUM(amount)) OVER (
#            PARTITION BY fiscal_year, fiscal_quarter, segment_code, predicted_category
#          ), 0), 2) AS hhi_contribution
#   FROM spend
#   GROUP BY fiscal_year, fiscal_quarter, segment_code, predicted_category, supplier_id
# ),
# maverick AS (
#   SELECT fiscal_year, fiscal_quarter, segment_code, predicted_category,
#          SUM(CASE WHEN supplier_primary_category <> predicted_category
#                   THEN amount ELSE 0 END) AS maverick_spend,
#          SUM(amount) AS total_spend
#   FROM spend
#   GROUP BY fiscal_year, fiscal_quarter, segment_code, predicted_category
# ),
# off_contract AS (
#   -- Spend from suppliers that don't have an ACTIVE inbound contract covering them
#   SELECT s.fiscal_year, s.fiscal_quarter, s.segment_code, s.predicted_category,
#          SUM(CASE WHEN ci.contract_workspace_id IS NULL THEN s.amount ELSE 0 END) AS off_contract_spend
#   FROM spend s
#   LEFT JOIN `{catalog}`.`{schema_silver}`.contract_inbound ci
#     ON s.supplier_id = ci.supplier_id
#    AND ci.status = 'Active'
#   GROUP BY s.fiscal_year, s.fiscal_quarter, s.segment_code, s.predicted_category
# )
# SELECT ...
# """)

print("TODO: build vw_sourcing_strategy")

# COMMAND ----------
# MAGIC %md ## Companion tables (optional)
# MAGIC
# MAGIC - `gold.fact_category_supplier_concentration` — materialized version of the
# MAGIC   per-category Herfindahl index (useful for time-series dashboarding).
# MAGIC - `gold.fact_maverick_offenders` — per-supplier maverick spend ranked.

# COMMAND ----------
# TODO: optional materializations
print("TODO: optional companion tables")
