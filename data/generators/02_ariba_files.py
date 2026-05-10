# Databricks notebook source
# MAGIC %md
# MAGIC # Generator: SAP Ariba-shaped CSV files
# MAGIC
# MAGIC Writes CSVs to /Volumes/${catalog}/${schema_raw}/${raw_volume}/sap_ariba/:
# MAGIC   LFA1_SUPPLIER_MASTER, EKKO_PO_HEADER, EKPO_PO_LINE, RBKP_INVOICE_HEADER,
# MAGIC   ARIBA_SOURCING_EVENT, ARIBA_CONTRACT_WORKSPACE, ARIBA_SUPPLIER_PERFORMANCE.
# MAGIC
# MAGIC Monthly transaction volume + amount distribution scaled by macro factors
# MAGIC and normalized so per-quarter sums match _meta.dim_period_anchors within ±2%.
# MAGIC
# MAGIC Implementation deferred to next step.

# COMMAND ----------
dbutils.widgets.text("catalog", "finance_demo")
dbutils.widgets.text("schema_raw", "raw_data")
dbutils.widgets.text("schema_meta", "_meta")
dbutils.widgets.text("raw_volume", "files")

print("TODO: generate SAP Ariba CSVs")
