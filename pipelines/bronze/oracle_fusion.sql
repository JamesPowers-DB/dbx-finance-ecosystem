-- ============================================================================
-- BRONZE — Oracle Fusion Cloud (accounting)
-- ============================================================================
-- Target schema: ${schema_bronze_fusion}
-- Reads files from: /Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/
-- Naming convention: snake_case with prefixes (gl_*, ap_*, ar_*)
--
-- Pattern: MATERIALIZED VIEW for flat one-shot files; STREAMING TABLE for
-- per-quarter wildcard globs.
-- ============================================================================

-- ---- Flat reference files (batch read) -------------------------------------

CREATE OR REFRESH MATERIALIZED VIEW ${schema_bronze_fusion}.gl_periods
COMMENT "Oracle GL period calendar. Open vs Closed status drives FP&A actuals materialization."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/gl_periods.csv",
  format => "csv", header => true, inferColumnTypes => true);

CREATE OR REFRESH MATERIALIZED VIEW ${schema_bronze_fusion}.gl_code_combinations
COMMENT "7-segment chart of accounts. Maps cost centers → entities → segments → natural accounts; the join key for fact_gl_entries."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/gl_code_combinations.csv",
  format => "csv", header => true, inferColumnTypes => true);

CREATE OR REFRESH MATERIALIZED VIEW ${schema_bronze_fusion}.ap_supplier_sites_all
COMMENT "Oracle Payables supplier sites. Address-level data for supplier entity resolution (Phase 2 ML)."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/ap_supplier_sites_all.csv",
  format => "csv", header => true, inferColumnTypes => true);

CREATE OR REFRESH MATERIALIZED VIEW ${schema_bronze_fusion}.ar_customer_sites_all
COMMENT "Oracle Receivables customer sites. Bill-to / ship-to addresses for customer-side analytics."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/ar_customer_sites_all.csv",
  format => "csv", header => true, inferColumnTypes => true);

-- ---- Per-quarter files (streaming Auto Loader) -----------------------------

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_fusion}.gl_je_headers
COMMENT "Oracle GL journal entry headers (per-quarter files). Source attribute distinguishes Payables vs Receivables vs Manual postings."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/gl_je_headers_*.csv",
  format => "csv", header => true, inferColumnTypes => true);

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_fusion}.gl_je_lines
COMMENT "Oracle GL journal entry lines (per-quarter parquet). Always balanced per je_header_id (Σdr − Σcr = 0)."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/gl_je_lines_*.parquet",
  format => "parquet");

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_fusion}.gl_trial_balance
COMMENT "Period-end trial balance summary by code_combination_id. Roll-up validation against fact_gl_entries."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/gl_trial_balance_*.csv",
  format => "csv", header => true, inferColumnTypes => true);

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_fusion}.gl_balances
COMMENT "Aggregate GL balances by code_combination_id × period."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/gl_balances_*.parquet",
  format => "parquet");

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

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_fusion}.ar_invoices_all
COMMENT "Oracle Receivables customer invoices (per-quarter). Drives the revenue side of FP&A actuals."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/ar_invoices_all_*.csv",
  format => "csv", header => true, inferColumnTypes => true);
