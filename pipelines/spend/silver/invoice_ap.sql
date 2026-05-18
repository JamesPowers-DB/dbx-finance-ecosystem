-- ============================================================================
-- SILVER — invoice_ap (invoice LINE grain)
-- ============================================================================
-- One row per invoice line. Joins Fusion ap_invoice_lines_all (line) with
-- ap_invoices_all (header) for payment + status fields. Drops the old
-- ap_invoice_distributions_all layer per redesign.
--
-- Carries everything needed for AP-ops analytics + ML-training payload:
-- payment_terms, due_date, payment_date, payment_status; line_description,
-- quantity, unit_price; po_line_id (matched invoices) → silver.purchase_order;
-- _true_spend_category (the supervised label).
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_silver}.invoice_ap
COMMENT "AP invoice LINE grain. Headers joined for payment_terms / due_date / payment_date / payment_status; line carries description, amount, GL coding, and the ML label."
AS
SELECT
  'oracle_fusion'                                              AS source_system,
  'ap_invoice_lines_all+ap_invoices_all'                       AS source_table,
  CAST(l.invoice_line_id AS STRING)                            AS source_primary_key,
  CAST(l.invoice_line_id AS BIGINT)                            AS invoice_line_id,
  CAST(l.invoice_id AS BIGINT)                                 AS invoice_id,
  h.invoice_num                                                AS invoice_number,
  CAST(l.line_number AS INT)                                   AS line_number,
  l.line_type_lookup_code                                      AS line_type,

  -- header attributes
  h.vendor_id_ext                                              AS supplier_id,
  h.po_matched_flag,
  CAST(h.source_po_header_id AS BIGINT)                        AS source_po_header_id,
  CAST(l.po_line_id AS BIGINT)                                 AS po_line_id,
  CAST(h.invoice_date AS DATE)                                 AS invoice_date,
  CAST(h.gl_date AS DATE)                                      AS gl_date,
  h.period_name,
  h.payment_terms_name                                         AS payment_terms,
  CAST(h.due_date AS DATE)                                     AS due_date,
  CAST(h.payment_date AS DATE)                                 AS payment_date,
  h.payment_status_flag                                        AS payment_status,
  h.invoice_currency                                           AS currency,

  -- derived AP-ops fields (NULL when unpaid)
  CASE
    WHEN h.payment_date IS NULL THEN NULL
    WHEN h.payment_date <= h.due_date THEN TRUE
    ELSE FALSE
  END                                                          AS is_on_time_payment,
  CASE
    WHEN h.payment_date IS NULL THEN NULL
    ELSE DATEDIFF(h.payment_date, h.invoice_date)
  END                                                          AS days_to_pay,

  -- line-level fields
  l.item_description                                           AS line_description,
  CAST(l.quantity AS DECIMAL(18, 3))                           AS quantity,
  CAST(l.unit_price AS DECIMAL(18, 2))                         AS unit_price,
  CAST(l.amount AS DECIMAL(18, 2))                             AS amount,
  CAST(l.code_combination_id AS BIGINT)                        AS code_combination_id,
  l._segment_code                                              AS segment_code,
  l._true_spend_category                                       AS true_spend_category,

  YEAR(h.invoice_date)                                         AS fiscal_year,
  QUARTER(h.invoice_date)                                      AS fiscal_quarter
FROM ${schema_bronze_fusion}.ap_invoice_lines_all l
JOIN ${schema_bronze_fusion}.ap_invoices_all h
  ON l.invoice_id = h.invoice_id;
