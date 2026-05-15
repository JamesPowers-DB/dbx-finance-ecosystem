-- ============================================================================
-- GOLD — fact_fpa_actuals (per-period × segment × account-type roll-up)
-- ============================================================================
-- Aggregates fact_gl_entries to the FP&A grain: one row per
-- (fiscal_year, fiscal_quarter, segment, account_type). Revenue is reported
-- positive; expense types (COGS / SGA / RD / INTEREST / TAX) are reported
-- positive (debit-natural).
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.fact_fpa_actuals
COMMENT "FP&A actuals from GL. Should reconcile to _meta.dim_period_anchors per (fiscal_year × fiscal_quarter × segment_code × account_type) ±2%."
AS
SELECT
  fiscal_year,
  fiscal_quarter,
  segment_code,
  account_type,
  -- Revenue accounts are credit-natural; reverse sign so they display positive
  CASE
    WHEN account_type = 'REVENUE' THEN SUM(accounted_cr - accounted_dr)
    ELSE                                SUM(accounted_dr - accounted_cr)
  END                                              AS amount_usd,
  COUNT(*)                                         AS entry_count
FROM ${schema_gold}.fact_gl_entries
WHERE segment_code IS NOT NULL
  AND account_type IN ('REVENUE', 'COGS', 'SGA', 'RD', 'INTEREST', 'TAX')
GROUP BY ALL;
