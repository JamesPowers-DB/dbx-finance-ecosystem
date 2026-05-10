# Databricks notebook source
# MAGIC %md
# MAGIC # Generator: Oracle Fusion Cloud-shaped CSV + Parquet files
# MAGIC
# MAGIC Writes to /Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/:
# MAGIC   gl_je_headers/lines, gl_code_combinations, gl_periods, gl_balances,
# MAGIC   gl_trial_balance, xla_ae_*, ap_*, ar_*.
# MAGIC
# MAGIC Implementation deferred to next step.

# COMMAND ----------
dbutils.widgets.text("catalog", "finance_demo")
dbutils.widgets.text("schema_raw", "raw_data")
dbutils.widgets.text("schema_meta", "_meta")
dbutils.widgets.text("raw_volume", "files")

print("TODO: generate Oracle Fusion CSV + Parquet")
