# Databricks notebook source
# MAGIC %md
# MAGIC # Generator: seed _meta.dim_period_anchors from Honeywell 10-K/10-Q
# MAGIC
# MAGIC Hand-curates FY2023, FY2024, plus each available quarter through latest
# MAGIC 10-Q. Applies 1/10 scaling and Helios Industrial Group anonymization
# MAGIC (HAD/HPA/HSB/HET segment renaming, NA/EMEA/APAC/LATAM geographies) at
# MAGIC load time. Outputs one row per (period_type, period_end_date, segment_code).
# MAGIC
# MAGIC Implementation deferred to next step.

# COMMAND ----------
dbutils.widgets.text("catalog", "finance_demo")
dbutils.widgets.text("schema_meta", "_meta")

catalog = dbutils.widgets.get("catalog")
schema_meta = dbutils.widgets.get("schema_meta")

print(f"TODO: seed {catalog}.{schema_meta}.dim_period_anchors")
