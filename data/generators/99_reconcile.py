# Databricks notebook source
# MAGIC %md
# MAGIC # Reconciliation gate
# MAGIC
# MAGIC For every (fiscal_year, fiscal_quarter, segment_code) row in
# MAGIC _meta.dim_period_anchors, aggregate raw revenue and spend totals from
# MAGIC the generated files. Assert that aggregates land within ±${tolerance_pct}%
# MAGIC of anchor primary metrics (revenue, cogs + sga + rd).
# MAGIC
# MAGIC Job fails if any anchor metric drifts beyond tolerance. This is the
# MAGIC enforced contract that replaces the spot-check tie-outs from the old demo.
# MAGIC
# MAGIC Implementation deferred to next step.

# COMMAND ----------
dbutils.widgets.text("catalog", "finance_demo")
dbutils.widgets.text("schema_raw", "raw_data")
dbutils.widgets.text("schema_meta", "_meta")
dbutils.widgets.text("raw_volume", "files")
dbutils.widgets.text("tolerance_pct", "2.0")

print("TODO: assert anchor tie-out")
