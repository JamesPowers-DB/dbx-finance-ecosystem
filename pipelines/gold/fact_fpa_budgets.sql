-- ============================================================================
-- GOLD — fact_fpa_budgets (synthetic — prior-quarter actuals × growth factor)
-- ============================================================================
-- Demo budgets simulate trend-continuation forecasting: each quarter's budget
-- is the prior quarter's actuals × a per-account-type growth factor (revenue
-- 1.03, expense 1.02) × small noise. This intentionally misses macro turning
-- points (which is realistic for budget-vs-actual variance demos).
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.fact_fpa_budgets
COMMENT "Synthetic FP&A budgets. Trend-continuation from prior-quarter actuals so budget-vs-actual variance is non-trivial during macro shifts."
AS
WITH a AS (
  SELECT fiscal_year, fiscal_quarter, segment_code, account_type, amount_usd
  FROM ${schema_gold}.fact_fpa_actuals
)
SELECT
  fiscal_year,
  fiscal_quarter,
  segment_code,
  account_type,
  CAST(
    LAG(amount_usd) OVER (
      PARTITION BY segment_code, account_type
      ORDER BY fiscal_year, fiscal_quarter
    ) * CASE WHEN account_type = 'REVENUE' THEN 1.03 ELSE 1.02 END
    AS DECIMAL(18,2)
  ) AS amount_usd
FROM a;
