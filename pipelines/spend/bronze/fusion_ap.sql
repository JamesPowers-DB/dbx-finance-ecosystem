-- ============================================================================
-- BRONZE — Oracle Fusion AP (Accounts Payable invoices + distributions)
-- ============================================================================
-- Target schema: ${schema_bronze_fusion}
-- Reads files from: /Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/
-- ============================================================================

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_fusion}.ap_invoices_all
COMMENT "Oracle Payables invoice headers (per-quarter). po_matched_flag distinguishes 3-way-match vs direct vouchers."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/ap_invoices_all_*.csv",
  format => "csv", header => true, inferColumnTypes => true);

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_fusion}.ap_invoice_distributions_all
COMMENT "Oracle Payables invoice distribution lines (per-quarter parquet). Splits each invoice across multiple code_combination_ids for GL posting."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/ap_invoice_distributions_all_*.parquet",
  format => "parquet");
