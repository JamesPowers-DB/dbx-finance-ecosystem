# Databricks notebook source
# MAGIC %md
# MAGIC # Generator: dim_macro_environment
# MAGIC
# MAGIC Hand-engineered macro arc (GDP, inflation, demand_idx_sales/mfg/back_office,
# MAGIC supply_chain_stress, labor_market_tightness, seasonality) used to *shape*
# MAGIC monthly distribution of synthetic transactions within each quarter. Totals
# MAGIC per quarter are pinned by _meta.dim_period_anchors, not by this table.
# MAGIC
# MAGIC Implementation deferred to next step (databricks-data-generation skill).

# COMMAND ----------
dbutils.widgets.text("catalog", "finance_demo")
dbutils.widgets.text("schema_gold", "gold")

catalog = dbutils.widgets.get("catalog")
schema_gold = dbutils.widgets.get("schema_gold")

print(f"TODO: write {catalog}.{schema_gold}.dim_macro_environment")
