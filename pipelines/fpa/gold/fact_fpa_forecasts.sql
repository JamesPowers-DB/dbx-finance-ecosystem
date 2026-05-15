-- ============================================================================
-- GOLD — fact_fpa_forecasts (blend of budget + realized signal)
-- ============================================================================
-- forecast = 0.5 × budget + 0.5 × prior-quarter actuals — represents a
-- mid-quarter refresh that incorporates the most recent realized signal.
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.fact_fpa_forecasts
COMMENT "Blended FP&A forecast: 0.5 × budget + 0.5 × prior-quarter actuals. Catches turning points better than budget alone."
AS
WITH a AS (
  SELECT fiscal_year, fiscal_quarter, segment_code, account_type,
         amount_usd AS actuals_amount
  FROM ${schema_gold}.fact_fpa_actuals
),
b AS (
  SELECT fiscal_year, fiscal_quarter, segment_code, account_type,
         amount_usd AS budget_amount
  FROM ${schema_gold}.fact_fpa_budgets
),
prior_actuals AS (
  SELECT fiscal_year, fiscal_quarter, segment_code, account_type,
         LAG(actuals_amount) OVER (
           PARTITION BY segment_code, account_type
           ORDER BY fiscal_year, fiscal_quarter
         ) AS prior_amount
  FROM a
)
SELECT
  COALESCE(b.fiscal_year, p.fiscal_year)         AS fiscal_year,
  COALESCE(b.fiscal_quarter, p.fiscal_quarter)   AS fiscal_quarter,
  COALESCE(b.segment_code, p.segment_code)       AS segment_code,
  COALESCE(b.account_type, p.account_type)       AS account_type,
  CAST(
    0.5 * COALESCE(b.budget_amount, 0)
    + 0.5 * COALESCE(p.prior_amount, b.budget_amount, 0)
    AS DECIMAL(18,2)
  )                                              AS amount_usd
FROM b
FULL OUTER JOIN prior_actuals p
  USING (fiscal_year, fiscal_quarter, segment_code, account_type);
