# Databricks notebook source
# MAGIC %md
# MAGIC # Spend classification — sourcing-strategy gold view (2-tier)
# MAGIC
# MAGIC Creates `<catalog>.gold.vw_sourcing_strategy` — the *value-delivered*
# MAGIC layer that sourcing organizations consume. Built on top of the
# MAGIC ML-classified `fact_invoices` (after `batch_inference.py` populates
# MAGIC `<catalog>.ml.invoice_classifications`).
# MAGIC
# MAGIC The 2-tier taxonomy maps cleanly to the sourcing audience:
# MAGIC
# MAGIC - **Primary (parent) tier** drives executive summary views — "how much do
# MAGIC   we spend on Professional Services as a whole?"
# MAGIC - **Secondary (leaf) tier** drives category-manager negotiation views —
# MAGIC   "of the Professional Services spend, what's Legal vs. Audit vs. Consulting?"
# MAGIC
# MAGIC Four analytics surfaced by the view:
# MAGIC
# MAGIC 1. **Parent-tier concentration** — spend rolled up to parent × segment;
# MAGIC    where are we concentrated?
# MAGIC 2. **Leaf-tier supplier share** — within each leaf, Herfindahl index over
# MAGIC    suppliers for monopsony risk.
# MAGIC 3. **Maverick spend per leaf** — total $ where supplier's `category_primary`
# MAGIC    hint doesn't match the predicted leaf.
# MAGIC 4. **Off-contract category spend** — joined with `silver.contract_inbound`
# MAGIC    to flag spend not covered by an active inbound contract.
# MAGIC
# MAGIC Filtered to `addressability = 'Addressable'` — regulated suppliers
# MAGIC (utilities, government) aren't sourcing's to negotiate.

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
#     fi.predicted_primary_category,
#     fi.predicted_secondary_category,
#     fi.primary_confidence,
#     fi.secondary_confidence,
#     fi.supplier_id, fi.supplier_name,
#     fi.addressability,
#     fi.direct_indirect,
#     fi.amount,
#     ds.category_primary AS supplier_primary_category
#   FROM `{catalog}`.`{schema_gold}`.fact_invoices fi
#   LEFT JOIN `{catalog}`.`{schema_gold}`.dim_supplier ds USING (supplier_id)
#   WHERE fi.predicted_secondary_category IS NOT NULL
#     AND fi.addressability = 'Addressable'   -- exclude regulated suppliers
# ),
# parent_concentration AS (
#   -- Executive view: spend by parent × segment
#   SELECT
#     fiscal_year, fiscal_quarter, segment_code,
#     predicted_primary_category,
#     SUM(amount) AS parent_spend,
#     COUNT(DISTINCT supplier_id) AS suppliers_in_parent
#   FROM spend
#   GROUP BY fiscal_year, fiscal_quarter, segment_code, predicted_primary_category
# ),
# leaf_supplier_share AS (
#   -- Category-manager view: within each leaf, how concentrated is supplier spend?
#   SELECT fiscal_year, fiscal_quarter, segment_code,
#          predicted_primary_category, predicted_secondary_category, supplier_id,
#          SUM(amount) AS supplier_spend_in_leaf,
#          SUM(SUM(amount)) OVER (
#            PARTITION BY fiscal_year, fiscal_quarter, segment_code, predicted_secondary_category
#          ) AS leaf_total,
#          POW(SUM(amount) / NULLIF(SUM(SUM(amount)) OVER (
#            PARTITION BY fiscal_year, fiscal_quarter, segment_code, predicted_secondary_category
#          ), 0), 2) AS hhi_contribution
#   FROM spend
#   GROUP BY fiscal_year, fiscal_quarter, segment_code,
#            predicted_primary_category, predicted_secondary_category, supplier_id
# ),
# maverick AS (
#   -- Suppliers buying outside their primary category (leaf grain — more interesting at leaf)
#   SELECT fiscal_year, fiscal_quarter, segment_code,
#          predicted_primary_category, predicted_secondary_category,
#          SUM(CASE WHEN supplier_primary_category <> predicted_secondary_category
#                   THEN amount ELSE 0 END) AS maverick_spend,
#          SUM(amount) AS total_spend
#   FROM spend
#   GROUP BY fiscal_year, fiscal_quarter, segment_code,
#            predicted_primary_category, predicted_secondary_category
# ),
# off_contract AS (
#   -- Spend from suppliers that don't have an ACTIVE inbound contract covering them
#   SELECT s.fiscal_year, s.fiscal_quarter, s.segment_code,
#          s.predicted_primary_category, s.predicted_secondary_category,
#          SUM(CASE WHEN ci.contract_workspace_id IS NULL THEN s.amount ELSE 0 END) AS off_contract_spend
#   FROM spend s
#   LEFT JOIN `{catalog}`.`{schema_silver}`.contract_inbound ci
#     ON s.supplier_id = ci.supplier_id
#    AND ci.status = 'Active'
#   GROUP BY s.fiscal_year, s.fiscal_quarter, s.segment_code,
#            s.predicted_primary_category, s.predicted_secondary_category
# )
# SELECT ...
# """)

print("TODO: build vw_sourcing_strategy")

# COMMAND ----------
# MAGIC %md ## Companion tables (optional)
# MAGIC
# MAGIC - `gold.fact_category_supplier_concentration` — materialized version of the
# MAGIC   per-leaf Herfindahl index (useful for time-series dashboarding).
# MAGIC - `gold.fact_maverick_offenders` — per-supplier maverick spend ranked.
# MAGIC - `gold.fact_parent_rollup` — pre-aggregated parent-tier surface for the
# MAGIC   exec dashboard (parent × segment × quarter).

# COMMAND ----------
# TODO: optional materializations
print("TODO: optional companion tables")
