-- ============================================================================
-- BRONZE — Oracle Fusion AR (Accounts Receivable invoices)
-- ============================================================================
-- Target schema: ${schema_bronze_fusion}
-- ============================================================================

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_fusion}.ar_invoices_all
COMMENT "Oracle Receivables customer invoices (per-quarter). Drives the revenue side of FP&A actuals."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/ar_invoices_all_*.csv",
  format => "csv", header => true, inferColumnTypes => true);
