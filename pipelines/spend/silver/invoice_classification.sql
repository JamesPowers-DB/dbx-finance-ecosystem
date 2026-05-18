-- ============================================================================
-- SILVER — invoice_classification (ML inference results staging)
-- ============================================================================
-- Reads the ML batch-inference output table at <catalog>.<schema_ml>.invoice_classifications.
-- gold.fact_invoices LEFT JOINs this view; if batch inference hasn't run yet,
-- the view is empty and predictions show as NULL on every fact_invoices row.
--
-- The underlying ml.invoice_classifications table is initialized empty by
-- the generate_data job (01_period_anchors_seed.py creates the schema +
-- the table if missing). Batch inference (`ml/spend_classification/batch_inference.py`)
-- MERGEs into it.
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_silver}.invoice_classification
COMMENT "ML inference output for invoice lines. Populated by batch_inference.py; LEFT-joined to fact_invoices. Empty when inference hasn't run."
AS
SELECT
  CAST(invoice_line_id AS BIGINT)              AS invoice_line_id,
  predicted_category,
  CAST(classification_confidence AS DOUBLE)    AS classification_confidence,
  model_version,
  CAST(scored_at AS TIMESTAMP)                 AS scored_at
FROM ${catalog}.${schema_ml}.invoice_classifications;
