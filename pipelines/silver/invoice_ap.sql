-- ============================================================================
-- SILVER — invoice_ap (supplier-side invoices, conformed)
-- ============================================================================
-- Unions Ariba RBKP (raw arrival) + Fusion ap_invoices_all (posted to GL).
-- Same invoices may appear in both — silver dedups by (invoice_number).
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_silver}.invoice_ap
COMMENT "Conformed AP invoices. Dedup'd across Ariba (arrival) and Fusion (posted) views."
AS
WITH ariba_inv AS (
  SELECT
    'sap_ariba'        AS source_system,
    'RBKP_INVOICE_HEADER' AS source_table,
    BELNR              AS invoice_number,
    EBELN              AS po_number,
    LIFNR              AS supplier_id,
    BUKRS              AS buyer_company_code,
    CAST(BLDAT AS DATE) AS invoice_date,
    CAST(BUDAT AS DATE) AS posting_date,
    CAST(ZFBDT AS DATE) AS due_date,
    CAST(WRBTR AS DECIMAL(18,2)) AS gross_amount,
    WAERS              AS currency,
    'Y'                AS po_matched_flag,
    NULL               AS period_name,
    NULL               AS payment_status
  FROM ${schema_bronze_ariba}.RBKP_INVOICE_HEADER
),
fusion_inv AS (
  SELECT
    'oracle_fusion'                          AS source_system,
    'ap_invoices_all'                        AS source_table,
    invoice_num                              AS invoice_number,
    NULL                                     AS po_number,
    vendor_id_ext                            AS supplier_id,
    NULL                                     AS buyer_company_code,
    CAST(invoice_date AS DATE)               AS invoice_date,
    CAST(gl_date AS DATE)                    AS posting_date,
    CAST(NULL AS DATE)                       AS due_date,
    CAST(invoice_amount AS DECIMAL(18,2))    AS gross_amount,
    invoice_currency                         AS currency,
    po_matched_flag,
    period_name,
    payment_status
  FROM ${schema_bronze_fusion}.ap_invoices_all
)
SELECT
  -- Prefer Fusion fields when both present (Fusion is the system of record post-posting)
  COALESCE(f.invoice_number, a.invoice_number)                AS invoice_number,
  COALESCE(a.po_number, f.po_number)                          AS po_number,
  COALESCE(a.supplier_id, f.supplier_id)                      AS supplier_id,
  COALESCE(a.buyer_company_code, f.buyer_company_code)        AS buyer_company_code,
  CASE COALESCE(a.buyer_company_code, f.buyer_company_code)
    WHEN '1100' THEN 'HAD' WHEN '1200' THEN 'HPA'
    WHEN '1300' THEN 'HSB' WHEN '1400' THEN 'HET'
    WHEN '1900' THEN 'CORP' ELSE 'OTHER'
  END                                                         AS segment_code,
  COALESCE(f.invoice_date, a.invoice_date)                    AS invoice_date,
  COALESCE(f.posting_date, a.posting_date)                    AS posting_date,
  a.due_date,
  COALESCE(f.gross_amount, a.gross_amount)                    AS gross_amount,
  COALESCE(f.currency, a.currency)                            AS currency,
  COALESCE(f.po_matched_flag, a.po_matched_flag)              AS po_matched_flag,
  f.period_name,
  f.payment_status,
  YEAR(COALESCE(f.invoice_date, a.invoice_date))              AS fiscal_year,
  QUARTER(COALESCE(f.invoice_date, a.invoice_date))           AS fiscal_quarter,
  CASE
    WHEN f.invoice_number IS NOT NULL AND a.invoice_number IS NOT NULL THEN 'both'
    WHEN f.invoice_number IS NOT NULL                                  THEN 'oracle_fusion'
    ELSE 'sap_ariba'
  END                                                         AS source_systems
FROM fusion_inv f
FULL OUTER JOIN ariba_inv a
  ON f.invoice_number = a.invoice_number;
