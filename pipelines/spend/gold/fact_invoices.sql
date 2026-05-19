-- ============================================================================
-- GOLD — fact_invoices (AP-invoice LINE grain)
-- ============================================================================
-- This is the unit of spend in the redesigned model: invoices are the truth of
-- what we actually paid for. fact_purchase_orders is committed spend; this is
-- realized spend.
--
-- Classification surfaces three independent dimensions:
--
--   1. Direct vs. Indirect    — rule-based off the GL natural account.
--                               Direct = booked to a COGS account (product input).
--                               Indirect = booked elsewhere (SGA, R&D, etc.).
--
--   2. Addressable vs. Non-Addressable
--      Non-addressable = supplier flagged regulated (utilities, government
--                        fees, single-source compliance — sourcing can't move
--                        it). ~8% of suppliers by config.
--      Addressable     = everything else (sourcing can negotiate / consolidate).
--
--   3. Spend category (2-tier: 8 parents × 30 leaves)
--      - true_category_primary / true_category_secondary    → demo-only ground truth
--      - predicted_primary_category / predicted_secondary_category → ML output
--        (LEFT JOIN to silver.invoice_classification, NULL until inference runs)
--
-- IMPORTANT (demo vs. reality): true_category_* would NOT exist on real
-- Helios AP data. They're here so the demo can train a supervised classifier
-- against a deterministic label set. In a production engagement the customer
-- would supply a partial manually-curated training set instead.
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.fact_invoices
COMMENT "AP invoice LINE fact. Realized-spend surface + ML training payload. true_category_* are demo-only ground truth; in production these come from a manually-curated training set, not source-system data."
AS
WITH base AS (
  SELECT
    inv.invoice_line_id,
    inv.invoice_id,
    inv.invoice_number,
    inv.line_number,
    inv.line_type,
    inv.invoice_date,
    inv.gl_date,
    inv.period_name,
    inv.fiscal_year,
    inv.fiscal_quarter,
    inv.supplier_id,
    inv.po_matched_flag,
    inv.source_po_header_id,
    inv.po_line_id,
    inv.payment_terms,
    inv.due_date,
    inv.payment_date,
    inv.payment_status,
    inv.is_on_time_payment,
    inv.days_to_pay,
    inv.line_description,
    inv.quantity,
    inv.unit_price,
    inv.amount,
    inv.code_combination_id,
    inv.segment_code,
    inv.currency,
    inv.true_category_primary,
    inv.true_category_secondary
  FROM ${schema_silver}.invoice_ap inv
)
SELECT
  b.invoice_line_id,
  b.invoice_id,
  b.invoice_number,
  b.line_number,
  b.line_type,
  b.invoice_date,
  b.gl_date,
  b.period_name,
  b.fiscal_year,
  b.fiscal_quarter,
  b.segment_code,
  b.supplier_id,
  s.supplier_name,
  s.region                                  AS supplier_region,
  s.country_code                            AS supplier_country,
  s.maverick_propensity                     AS supplier_maverick_propensity,
  s.is_regulated_supplier,
  b.po_matched_flag,
  b.source_po_header_id,
  b.po_line_id,
  b.payment_terms,
  b.due_date,
  b.payment_date,
  b.payment_status,
  b.is_on_time_payment,
  b.days_to_pay,
  b.line_description,
  b.quantity,
  b.unit_price,
  b.amount,
  b.currency,
  b.code_combination_id,
  coa.segment3_natural_account              AS gl_account,
  coa.natural_account_type                  AS gl_account_type,

  -- Rule-based classifications (deterministic from GL account + supplier flag)
  CASE WHEN coa.natural_account_type = 'COGS' THEN 'Direct' ELSE 'Indirect' END
                                            AS direct_indirect,
  CASE WHEN COALESCE(s.is_regulated_supplier, FALSE) THEN 'Non-Addressable' ELSE 'Addressable' END
                                            AS addressability,

  -- Supervised labels (2-tier) — demo-only ground truth
  b.true_category_primary,
  b.true_category_secondary,

  -- ML predictions (LEFT JOIN — NULL when batch inference hasn't run)
  c.predicted_primary_category,
  c.predicted_secondary_category,
  c.primary_confidence,
  c.secondary_confidence,
  c.model_version,
  c.scored_at
FROM base b
LEFT JOIN ${schema_gold}.dim_supplier s
  ON b.supplier_id = s.supplier_id
LEFT JOIN ${schema_bronze_fusion}.gl_code_combinations coa
  ON b.code_combination_id = coa.code_combination_id
LEFT JOIN ${schema_silver}.invoice_classification c
  ON b.invoice_line_id = c.invoice_line_id;
