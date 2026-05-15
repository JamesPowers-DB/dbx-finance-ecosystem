-- ============================================================================
-- BRONZE — Oracle Fusion GL (general ledger journals, balances, COA, periods)
-- ============================================================================
-- Target schema: ${schema_bronze_fusion}
-- ============================================================================

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
