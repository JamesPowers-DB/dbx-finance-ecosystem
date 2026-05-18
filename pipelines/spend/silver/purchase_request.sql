-- ============================================================================
-- SILVER — purchase_request (PR line grain)
-- ============================================================================
-- Conformed PR lines from Ariba EBAN. One row per (PR number × PR line).
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_silver}.purchase_request
COMMENT "PR line items from Ariba EBAN. Released PRs (status='B') become POs in Fusion; cancelled PRs (status='L') stop here. PR amounts are estimates — final cost lives on the invoice."
AS
SELECT
  'sap_ariba'                                                       AS source_system,
  'EBAN_PR_HEADER+LINE'                                             AS source_table,
  CONCAT(l.BANFN, '/', LPAD(CAST(l.BNFPO AS STRING), 4, '0'))       AS source_primary_key,
  l.BANFN                                                           AS pr_number,
  CAST(l.BNFPO AS INT)                                              AS pr_line_num,
  h.BUKRS                                                           AS company_code,
  CASE h.BUKRS
    WHEN '1100' THEN 'HAD' WHEN '1200' THEN 'HPA'
    WHEN '1300' THEN 'HSB' WHEN '1400' THEN 'HET'
    WHEN '1900' THEN 'CORP' ELSE 'OTHER'
  END                                                               AS segment_code,
  h.AFNAM                                                           AS requester_id,
  CAST(h.ERDAT AS DATE)                                             AS pr_created_date,
  CAST(h.LFDAT AS DATE)                                             AS requested_delivery_date,
  h.BSART                                                           AS pr_doc_type,
  h.STATU                                                           AS pr_status_code,
  CASE h.STATU
    WHEN 'B' THEN 'released'
    WHEN 'L' THEN 'cancelled'
    WHEN 'N' THEN 'open'
    ELSE LOWER(h.STATU)
  END                                                               AS pr_status,
  l._supplier_intended                                              AS intended_supplier_id,
  l.MATNR                                                           AS material_number,
  l.MATGROUP                                                        AS material_group_code,
  l.TXZ01                                                           AS line_description,
  CAST(l.MENGE AS DECIMAL(18, 3))                                   AS quantity,
  l.MEINS                                                           AS uom,
  CAST(l.PREIS AS DECIMAL(18, 2))                                   AS estimated_unit_price,
  CAST(l.PEINH AS INT)                                              AS price_unit,
  l.WAERS                                                           AS currency,
  l._true_spend_category                                            AS true_spend_category,
  YEAR(h.ERDAT)                                                     AS fiscal_year,
  QUARTER(h.ERDAT)                                                  AS fiscal_quarter
FROM ${schema_bronze_ariba}.EBAN_PR_LINE l
JOIN ${schema_bronze_ariba}.EBAN_PR_HEADER h USING (BANFN);
