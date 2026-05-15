-- ============================================================================
-- GOLD — fact_trial_balance (period-end totals by COA combination)
-- ============================================================================
-- Derived from fact_gl_entries (preferred — single source of truth) rather
-- than the bronze gl_trial_balance file. Aggregation is one row per
-- (code_combination_id × fiscal_year × fiscal_quarter).
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.fact_trial_balance
COMMENT "Period-end trial balance roll-up by code_combination_id."
AS
SELECT
  code_combination_id,
  fiscal_year,
  fiscal_quarter,
  period_name,
  segment_code,
  account_type,
  natural_account_code,
  cost_center_code,
  SUM(accounted_dr)                AS period_dr,
  SUM(accounted_cr)                AS period_cr,
  SUM(net_amount)                  AS period_net
FROM ${schema_gold}.fact_gl_entries
WHERE code_combination_id IS NOT NULL
GROUP BY ALL;
