-- ============================================================================
-- SILVER — invoice_ar (customer-side invoices)
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_silver}.invoice_ar
COMMENT "Conformed AR invoices from Oracle Receivables. Drives revenue side of FP&A actuals."
AS
SELECT
  'oracle_fusion'                              AS source_system,
  'ar_invoices_all'                            AS source_table,
  CAST(customer_trx_id AS STRING)              AS source_primary_key,
  trx_number                                   AS invoice_number,
  cust_account_id_ext                          AS customer_id,
  CAST(trx_date AS DATE)                       AS invoice_date,
  CAST(gl_date AS DATE)                        AS posting_date,
  period_name,
  invoice_currency_code                        AS currency,
  CAST(total_amount AS DECIMAL(18,2))          AS total_amount,
  status,
  YEAR(trx_date)                               AS fiscal_year,
  QUARTER(trx_date)                            AS fiscal_quarter
FROM ${schema_bronze_fusion}.ar_invoices_all;
