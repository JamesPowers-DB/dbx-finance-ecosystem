-- ============================================================================
-- GOLD — fact_purchase_orders (PO line grain)
-- ============================================================================
-- Fusion PO line items with supplier + segment enrichment. PO commitments —
-- the "committed spend" pillar of P2P. Cross-system bridge: source_pr_number
-- FKs to fact_purchase_requests.pr_number (released-PR slice).
--
-- The ML hooks that used to live on fact_spend (unspsc, managed_spend_flag,
-- classification_confidence) MOVED to fact_invoices, since the redesign
-- classifies invoices — not POs — as the unit of spend.
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.fact_purchase_orders
COMMENT "PO-line commitment fact. Cross-system bridge: source_pr_number FKs to fact_purchase_requests.pr_number for the Ariba→Fusion view of the procurement chain."
AS
SELECT
  po.po_number,
  po.po_line_num,
  po.po_created_date,
  po.po_approved_date,
  po.fiscal_year,
  po.fiscal_quarter,
  po.po_doc_type,
  po.po_status,
  po.segment_code,
  po.supplier_id,
  s.supplier_name,
  s.region                                  AS supplier_region,
  s.country_code                            AS supplier_country,
  s.maverick_propensity                     AS supplier_maverick_propensity,
  s.segment_affinity                        AS supplier_segment_affinity,
  po.supplier_site_code,
  po.material_number,
  po.material_group_code,
  po.line_description,
  po.quantity,
  po.uom,
  po.unit_price,
  po.extended_amount,
  po.currency,
  po.source_pr_number,
  po.source_pr_line_num,
  po.true_spend_category
FROM ${schema_silver}.purchase_order po
LEFT JOIN ${schema_gold}.dim_supplier s
  ON po.supplier_id = s.supplier_id;
