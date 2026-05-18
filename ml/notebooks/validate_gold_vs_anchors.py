# Databricks notebook source
# MAGIC %md
# MAGIC # Gold-vs-anchor validation gate
# MAGIC
# MAGIC Runs after the lakehouse pipeline. For each (fiscal_year, fiscal_quarter,
# MAGIC segment_code) row in _meta.dim_period_anchors, computes the corresponding
# MAGIC aggregate from gold.fact_revenue and gold.fact_invoices, and asserts the
# MAGIC delta is within ±${tolerance_pct}%. Fails the job if any anchor drifts.
# MAGIC
# MAGIC Implementation deferred to next step.

# COMMAND ----------
dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema_gold", "")
dbutils.widgets.text("schema_meta", "")
dbutils.widgets.text("tolerance_pct", "2.0")

print("TODO: assert gold tables tie to anchors")
