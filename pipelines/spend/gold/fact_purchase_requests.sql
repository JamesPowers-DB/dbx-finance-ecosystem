-- ============================================================================
-- GOLD — fact_purchase_requests (PR-line grain)
-- ============================================================================
-- Ariba PR line items, enriched with supplier + segment dims. Use this fact
-- to measure intake volume, PR cancellation rates, and PR-to-PO conversion.
--
-- Status semantics:
--   pr_status = 'released'  → flowed to Fusion (FK present on fact_purchase_orders.source_pr_number)
--   pr_status = 'cancelled' → never reached Fusion (stops at PR layer)
--   pr_status = 'open'      → in-flight at extract time
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.fact_purchase_requests
COMMENT "Purchase Request line fact. Intake-side measurement (volume, cancel rates). PR amounts are estimates; final cost lives on fact_invoices."
AS
SELECT
  pr.pr_number,
  pr.pr_line_num,
  pr.pr_created_date,
  pr.requested_delivery_date,
  pr.fiscal_year,
  pr.fiscal_quarter,
  pr.segment_code,
  pr.company_code,
  pr.pr_doc_type,
  pr.pr_status,
  pr.pr_status_code,
  pr.requester_id,
  pr.intended_supplier_id                  AS supplier_id,
  s.supplier_name,
  s.region                                 AS supplier_region,
  s.country_code                           AS supplier_country,
  pr.material_number,
  pr.material_group_code,
  pr.line_description,
  pr.quantity,
  pr.uom,
  pr.estimated_unit_price,
  pr.price_unit,
  CAST(pr.quantity * pr.estimated_unit_price AS DECIMAL(18, 2)) AS estimated_extended_amount,
  pr.currency,
  pr.true_spend_category
FROM ${schema_silver}.purchase_request pr
LEFT JOIN ${schema_gold}.dim_supplier s
  ON pr.intended_supplier_id = s.supplier_id;
