-- ============================================================================
-- SILVER — purchase_request (PR line grain)
-- ============================================================================
-- Conformed PR lines from Ariba EBAN. One row per (PR number × PR line).
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema}.silver_purchase_request
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
    WHEN '1100' THEN 'AD' WHEN '1200' THEN 'PA'
    WHEN '1300' THEN 'SB' WHEN '1400' THEN 'ET'
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
  l._true_category_primary                                          AS true_category_primary,
  l._true_category_secondary                                        AS true_category_secondary,
  l._pr_source                                                      AS pr_source,
  l._contract_id                                                    AS contract_id,
  l._sourcing_event_id                                              AS sourcing_event_id,
  YEAR(h.ERDAT)                                                     AS fiscal_year,
  QUARTER(h.ERDAT)                                                  AS fiscal_quarter
FROM ${schema}.bronze_eban_pr_line l
JOIN ${schema}.bronze_eban_pr_header h USING (BANFN);
