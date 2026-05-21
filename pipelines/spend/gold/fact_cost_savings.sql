-- ============================================================================
-- GOLD — fact_cost_savings (auto-detected cost reductions from sourcing events)
-- ============================================================================
-- Auto-detection logic: for each Awarded sourcing event, the pre-negotiation
-- baseline is estimated from the event type — sourcing orgs typically achieve
-- different savings percentages by event type:
--   RFQ (price-competitive):   ~12% below the baseline ask
--   RFP (solution + price):    ~18% below the baseline ask
--   Auction (reverse auction): ~25% below the baseline ask
-- In production, the customer would supply actual pre-negotiation quotes from
-- Ariba. For this demo, the baseline is back-calculated so that
--   savings = awarded_amount / (1 - savings_factor) * savings_factor
--
-- Manual cost-avoidance entries are NOT in this view — they live in the
-- Lakebase app table `savings_avoidance_entries` and are joined client-side
-- by the portal's cost-savings router.
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.fact_cost_savings
COMMENT "Auto-detected cost reductions from closed sourcing events. Baseline is estimated from event type × awarded amount. Manual avoidance entries are stored in Lakebase and joined in the portal."
AS
WITH savings_rates AS (
  SELECT
    event_id,
    event_type,
    title,
    owner_org_unit,
    awarded_supplier_id                                   AS supplier_id,
    fiscal_year,
    fiscal_quarter,
    awarded_amount,
    -- Back-calculate baseline: awarded = baseline * (1 - rate), so baseline = awarded / (1 - rate)
    CASE event_type
      WHEN 'Auction' THEN 0.25
      WHEN 'RFP'     THEN 0.18
      ELSE                0.12
    END                                                   AS savings_rate,
    CASE event_type
      WHEN 'Auction' THEN ROUND(awarded_amount / (1.0 - 0.25), 2)
      WHEN 'RFP'     THEN ROUND(awarded_amount / (1.0 - 0.18), 2)
      ELSE                ROUND(awarded_amount / (1.0 - 0.12), 2)
    END                                                   AS baseline_amount
  FROM ${schema_silver}.sourcing_event
  WHERE status = 'Awarded'
    AND awarded_amount IS NOT NULL
    AND awarded_amount > 0
)
SELECT
  CONCAT('SE-', sr.event_id)                             AS savings_event_id,
  'sourcing_event'                                       AS source_type,
  sr.event_id                                            AS source_id,
  s.segment_affinity                                     AS segment_code,
  sr.fiscal_year,
  sr.fiscal_quarter,
  'reduction'                                            AS savings_type,
  s.category_primary,
  sr.supplier_id,
  s.supplier_name,
  sr.event_type,
  sr.title                                               AS event_title,
  sr.owner_org_unit,
  sr.awarded_amount,
  sr.baseline_amount,
  ROUND(sr.baseline_amount - sr.awarded_amount, 2)       AS savings_amount_usd,
  sr.savings_rate,
  NULL                                                   AS attested_by,
  NULL                                                   AS attested_at,
  CAST(NULL AS STRING)                                   AS notes
FROM savings_rates sr
LEFT JOIN ${schema_gold}.dim_supplier s
  ON sr.supplier_id = s.supplier_id;
