# Databricks notebook source
# MAGIC %md
# MAGIC # Regenerate a single fiscal quarter
# MAGIC
# MAGIC Triggered after a new anchor row is merged. Re-runs the per-source
# MAGIC generators (Ariba / Fusion / CMS) for the specified (fiscal_year,
# MAGIC fiscal_quarter) only, replacing the affected files in the raw volume.
# MAGIC The lakehouse pipeline can then be triggered with full_refresh=false
# MAGIC to propagate the new period through bronze → silver → gold.
# MAGIC
# MAGIC Implementation deferred to next step.

# COMMAND ----------
dbutils.widgets.text("catalog", "finance_demo")
dbutils.widgets.text("schema_raw", "raw_data")
dbutils.widgets.text("schema_meta", "_meta")
dbutils.widgets.text("raw_volume", "files")
dbutils.widgets.text("fiscal_year", "")
dbutils.widgets.text("fiscal_quarter", "")

print("TODO: regenerate quarter")
