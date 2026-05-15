-- ============================================================================
-- SILVER — purchase_order (line grain, ML feature payload)
-- ============================================================================
-- Joins Ariba EKKO header + EKPO line. One row per PO line — the grain the
-- spend-classification model is trained on.
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_silver}.purchase_order
COMMENT "PO line items conformed from Ariba EKKO/EKPO. Carries ML features (TXZ01, MATGROUP, supplier_id, amounts) and the supervised label (_true_spend_category)."
AS
SELECT
  'sap_ariba'                                                            AS source_system,
  'EKKO+EKPO'                                                            AS source_table,
  CONCAT(p.EBELN, '/', LPAD(CAST(p.EBELP AS STRING), 4, '0'))            AS source_primary_key,
  p.EBELN                                                                AS po_number,
  p.EBELP                                                                AS po_line_num,
  h.LIFNR                                                                AS supplier_id,
  h.BUKRS                                                                AS buyer_company_code,
  CASE h.BUKRS
    WHEN '1100' THEN 'HAD' WHEN '1200' THEN 'HPA'
    WHEN '1300' THEN 'HSB' WHEN '1400' THEN 'HET'
    WHEN '1900' THEN 'CORP' ELSE 'OTHER'
  END                                                                    AS segment_code,
  h.BSART                                                                AS po_doc_type,
  CAST(h.AEDAT AS DATE)                                                  AS po_created_date,
  CAST(h.BEDAT AS DATE)                                                  AS po_order_date,
  YEAR(h.AEDAT)                                                          AS fiscal_year,
  QUARTER(h.AEDAT)                                                       AS fiscal_quarter,
  p.MATNR                                                                AS material_number,
  p.MATGROUP                                                             AS material_group_code,
  p.TXZ01                                                                AS line_description,
  CAST(p.MENGE AS DECIMAL(18,3))                                         AS quantity,
  p.MEINS                                                                AS uom,
  CAST(p.NETPR AS DECIMAL(18,2))                                         AS unit_price,
  p.PEINH                                                                AS price_unit,
  CAST(p.NETWR AS DECIMAL(18,2))                                         AS extended_amount,
  p.WAERS                                                                AS currency,
  p._true_spend_category                                                 AS true_spend_category
FROM ${schema_bronze_ariba}.EKPO_PO_LINE p
JOIN ${schema_bronze_ariba}.EKKO_PO_HEADER h USING (EBELN);
