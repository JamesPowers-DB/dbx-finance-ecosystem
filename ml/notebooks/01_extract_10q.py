# Databricks notebook source
# MAGIC %md
# MAGIC # 10-Q extractor
# MAGIC
# MAGIC Reads a 10-Q HTML filing from `${filing_path}`, calls ai_extract /
# MAGIC AI_QUERY (Claude) with a strict JSON schema matching the anchor columns,
# MAGIC and writes a draft row per segment + CONSOL to
# MAGIC `${catalog}.${schema_meta}.dim_period_anchors_draft` with a confidence_score.
# MAGIC
# MAGIC Numbers are extracted at the source-filing scale; the Helios renaming + 1/10
# MAGIC scaling are applied in the review step (02), not here. This keeps the
# MAGIC AI-extracted draft faithful to the source filing for easier diffing.
# MAGIC
# MAGIC Implementation deferred to next step.

# COMMAND ----------
dbutils.widgets.text("catalog", "finance_demo")
dbutils.widgets.text("schema_meta", "_meta")
dbutils.widgets.text("filing_path", "")
dbutils.widgets.text("fiscal_year", "")
dbutils.widgets.text("fiscal_quarter", "")

print("TODO: ai_extract 10-Q -> dim_period_anchors_draft")
