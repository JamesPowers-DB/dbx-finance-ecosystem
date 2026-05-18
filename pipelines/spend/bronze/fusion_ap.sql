-- ============================================================================
-- BRONZE — Oracle Fusion AP (invoice headers + invoice lines)
-- ============================================================================
-- Target schema: ${schema_bronze_fusion}
--
-- Header grain: ap_invoices_all (one row per invoice).
-- Line grain:   ap_invoice_lines_all (REPLACES ap_invoice_distributions_all
--                from the old design — the line layer is enough; we don't need
--                a separate distribution split).
--
-- Headers now carry: payment_terms_name, due_date, payment_date (NULL when
-- unpaid), payment_status_flag (PAID / OPEN_CURRENT / OPEN_PAST_DUE),
-- source_po_header_id (NULL for non-PO direct vouchers).
--
-- Lines carry: code_combination_id (GL posting), _segment_code,
-- _true_spend_category (the ML training label).
-- ============================================================================

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_fusion}.ap_invoices_all
COMMENT "Oracle Payables invoice headers. payment_status_flag drives AP ops metrics (on-time payment, DPO). po_matched_flag distinguishes PO-matched (Y) from non-PO direct vouchers (N)."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/ap_invoices_all_*.csv",
  format => "csv", header => true, inferColumnTypes => true);

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_fusion}.ap_invoice_lines_all
COMMENT "Oracle Payables invoice lines. The ML spend-classification model trains on this grain. Replaces the old ap_invoice_distributions_all layer."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/ap_invoice_lines_all_*.parquet",
  format => "parquet");
