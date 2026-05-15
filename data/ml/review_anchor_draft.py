# Databricks notebook source
# MAGIC %md
# MAGIC # Anchor draft review and merge
# MAGIC
# MAGIC Interactive notebook. Shows:
# MAGIC  - draft rows from `${catalog}.${schema_meta}.dim_period_anchors_draft`
# MAGIC    for the target (fiscal_year, fiscal_quarter)
# MAGIC  - QoQ diff vs prior accepted quarter
# MAGIC  - segment → CONSOL tie-out check
# MAGIC  - sign checks (revenue > 0, etc.)
# MAGIC  - confidence_score per field
# MAGIC
# MAGIC On accept: applies 1/10 scaling, applies Helios renaming, stamps
# MAGIC human_reviewed_by / human_reviewed_at, MERGEs into
# MAGIC `${catalog}.${schema_meta}.dim_period_anchors`.
# MAGIC
# MAGIC Implementation deferred to next step.

# COMMAND ----------
dbutils.widgets.text("catalog", "")
dbutils.widgets.text("schema_meta", "")
dbutils.widgets.text("fiscal_year", "")
dbutils.widgets.text("fiscal_quarter", "")

print("TODO: human-in-the-loop review + MERGE into dim_period_anchors")
