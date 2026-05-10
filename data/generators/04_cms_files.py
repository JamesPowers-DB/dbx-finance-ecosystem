# Databricks notebook source
# MAGIC %md
# MAGIC # Generator: In-house CMS-shaped JSON files
# MAGIC
# MAGIC Writes line-delimited JSON to /Volumes/${catalog}/${schema_raw}/${raw_volume}/inhouse_cms/:
# MAGIC   contract, contract_party, contract_line_item, contract_amendment,
# MAGIC   performance_obligation, billing_schedule.
# MAGIC
# MAGIC Implementation deferred to next step.

# COMMAND ----------
dbutils.widgets.text("catalog", "finance_demo")
dbutils.widgets.text("schema_raw", "raw_data")
dbutils.widgets.text("schema_meta", "_meta")
dbutils.widgets.text("raw_volume", "files")

print("TODO: generate in-house CMS JSON")
