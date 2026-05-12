-- ============================================================================
-- GOLD — fact_revenue (billing event grain)
-- ============================================================================
-- One row per CMS billing schedule event. Anchored to revenue per
-- (fiscal_year, fiscal_quarter, segment_code) within ±2%.
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.fact_revenue
COMMENT "Revenue fact at the CMS billing-event grain. Phase 2 reserves contract_leakage_flag (from inbound-contract leakage detection) and savings_realized_usd (from sourcing-event savings tracking)."
AS
SELECT
  b.schedule_id,
  b.contract_id,
  b.customer_id,
  b.segment_code,
  CAST(b.bill_date AS DATE)                AS bill_date,
  YEAR(b.bill_date)                        AS fiscal_year,
  QUARTER(b.bill_date)                     AS fiscal_quarter,
  CAST(b.amount AS DECIMAL(18,2))          AS amount,
  b.currency,
  b.status,
  c.contract_number,
  c.signed_date,
  c.start_date                             AS contract_start_date,
  c.end_date                               AS contract_end_date,
  c.effective_contract_value,
  -- Phase 2 hooks
  CAST(NULL AS BOOLEAN)   AS contract_leakage_flag,
  CAST(NULL AS DECIMAL(18,2)) AS savings_realized_usd
FROM ${schema_bronze_cms}.billing_schedule b
LEFT JOIN ${schema_silver}.contract_outbound c USING (contract_id);
