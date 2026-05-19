-- ============================================================================
-- SILVER — purchase_order (PO line grain) — sourced from Fusion
-- ============================================================================
-- One row per PO line. Source: Fusion po_lines_all + po_headers_all (re-pointed
-- from the old Ariba EKKO/EKPO model). Carries the source PR reference for the
-- Ariba → Fusion cross-system join.
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_silver}.purchase_order
COMMENT "PO lines from Fusion po_headers_all + po_lines_all. source_pr_number FKs to silver.purchase_request.pr_number for the Ariba bridge. 2-tier true_category_* labels propagate through from the upstream PR."
AS
SELECT
  'oracle_fusion'                                                   AS source_system,
  'po_headers_all+po_lines_all'                                     AS source_table,
  CAST(l.po_line_id AS STRING)                                      AS source_primary_key,
  CAST(l.po_header_id AS BIGINT)                                    AS po_header_id,
  CAST(l.po_line_id AS BIGINT)                                      AS po_line_id,
  h.segment1                                                        AS po_number,
  CAST(l.line_num AS INT)                                           AS po_line_num,
  h.vendor_id_ext                                                   AS supplier_id,
  h.vendor_site_code                                                AS supplier_site_code,
  h.type_lookup_code                                                AS po_doc_type,
  h.po_status                                                       AS po_status,
  CAST(h.creation_date AS DATE)                                     AS po_created_date,
  CAST(h.approved_date AS DATE)                                     AS po_approved_date,
  YEAR(h.approved_date)                                             AS fiscal_year,
  QUARTER(h.approved_date)                                          AS fiscal_quarter,
  l._segment_code                                                   AS segment_code,
  l.item_id_ext                                                     AS material_number,
  l.material_group_code                                             AS material_group_code,
  l.item_description                                                AS line_description,
  CAST(l.quantity_committed AS DECIMAL(18, 3))                      AS quantity,
  l.uom                                                             AS uom,
  CAST(l.unit_price AS DECIMAL(18, 2))                              AS unit_price,
  CAST(l.quantity_committed * l.unit_price AS DECIMAL(18, 2))       AS extended_amount,
  l.currency_code                                                   AS currency,
  l.source_pr_number_ext                                            AS source_pr_number,
  CAST(l.source_pr_line_num_ext AS INT)                             AS source_pr_line_num,
  l._true_category_primary                                          AS true_category_primary,
  l._true_category_secondary                                        AS true_category_secondary
FROM ${schema_bronze_fusion}.po_lines_all l
JOIN ${schema_bronze_fusion}.po_headers_all h USING (po_header_id);
