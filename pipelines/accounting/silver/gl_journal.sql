-- ============================================================================
-- SILVER — gl_journal_header + gl_journal_line
-- ============================================================================
-- Two tables in this file. Line grain joined with COA gives fact_gl_entries.
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_silver}.gl_journal_header
COMMENT "Conformed GL journal entry headers from Oracle Fusion."
AS
SELECT
  'oracle_fusion'                       AS source_system,
  'gl_je_headers'                       AS source_table,
  CAST(je_header_id AS STRING)          AS source_primary_key,
  CAST(je_header_id AS BIGINT)          AS je_header_id,
  period_name,
  ledger_id,
  je_source,
  je_category,
  posted_flag,
  CAST(posted_date AS DATE)             AS posted_date,
  currency_code,
  YEAR(posted_date)                     AS fiscal_year,
  QUARTER(posted_date)                  AS fiscal_quarter
FROM ${schema_bronze_fusion}.gl_je_headers;

CREATE OR REFRESH MATERIALIZED VIEW ${schema_silver}.gl_journal_line
COMMENT "Conformed GL journal entry lines. Balanced per je_header_id."
AS
SELECT
  'oracle_fusion'                                    AS source_system,
  'gl_je_lines'                                      AS source_table,
  CONCAT(CAST(je_header_id AS STRING), '/', CAST(je_line_num AS STRING)) AS source_primary_key,
  CAST(je_header_id AS BIGINT)                       AS je_header_id,
  je_line_num,
  CAST(code_combination_id AS BIGINT)                AS code_combination_id,
  CAST(entered_dr AS DECIMAL(18,2))                  AS entered_dr,
  CAST(entered_cr AS DECIMAL(18,2))                  AS entered_cr,
  CAST(accounted_dr AS DECIMAL(18,2))                AS accounted_dr,
  CAST(accounted_cr AS DECIMAL(18,2))                AS accounted_cr,
  CAST(accounted_dr - accounted_cr AS DECIMAL(18,2)) AS net_amount,
  description
FROM ${schema_bronze_fusion}.gl_je_lines;
