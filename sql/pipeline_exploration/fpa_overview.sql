-- ============================================================================
-- FP&A — actuals / budgets / forecasts exploration
-- ============================================================================
USE CATALOG horizontal_finance_dev;

-- Section 1 ------------------------------------------------------------------
-- Actuals by segment × fiscal quarter × account type.
SELECT
  fiscal_year,
  fiscal_quarter,
  segment_code,
  account_type,
  ROUND(amount_usd / 1e6, 2)          AS amount_mm,
  entry_count
FROM gold.fact_fpa_actuals
ORDER BY fiscal_year, fiscal_quarter, segment_code, account_type;

-- Section 2 ------------------------------------------------------------------
-- Side-by-side: actuals vs budget vs forecast for the most recent quarter.
WITH recent AS (
  SELECT MAX(fiscal_year * 10 + fiscal_quarter) AS fyq FROM gold.fact_fpa_actuals
)
SELECT
  a.fiscal_year,
  a.fiscal_quarter,
  a.segment_code,
  a.account_type,
  ROUND(a.amount_usd / 1e6, 2)        AS actual_mm,
  ROUND(b.amount_usd / 1e6, 2)        AS budget_mm,
  ROUND(f.amount_usd / 1e6, 2)        AS forecast_mm,
  ROUND((a.amount_usd - b.amount_usd) / NULLIF(b.amount_usd, 0) * 100, 1) AS var_act_vs_bud_pct,
  ROUND((a.amount_usd - f.amount_usd) / NULLIF(f.amount_usd, 0) * 100, 1) AS var_act_vs_fcst_pct
FROM gold.fact_fpa_actuals a
LEFT JOIN gold.fact_fpa_budgets b
  USING (fiscal_year, fiscal_quarter, segment_code, account_type)
LEFT JOIN gold.fact_fpa_forecasts f
  USING (fiscal_year, fiscal_quarter, segment_code, account_type)
WHERE (a.fiscal_year * 10 + a.fiscal_quarter) = (SELECT fyq FROM recent)
ORDER BY a.segment_code, a.account_type;

-- Section 3 ------------------------------------------------------------------
-- Year-over-year segment revenue growth.
WITH rev AS (
  SELECT fiscal_year, segment_code, SUM(amount_usd) AS revenue
  FROM gold.fact_fpa_actuals
  WHERE account_type = 'REVENUE'
  GROUP BY ALL
)
SELECT
  fiscal_year,
  segment_code,
  ROUND(revenue / 1e6, 2)             AS revenue_mm,
  ROUND(LAG(revenue) OVER (PARTITION BY segment_code ORDER BY fiscal_year) / 1e6, 2) AS prior_year_mm,
  ROUND(100.0 * (revenue - LAG(revenue) OVER (PARTITION BY segment_code ORDER BY fiscal_year))
                / NULLIF(LAG(revenue) OVER (PARTITION BY segment_code ORDER BY fiscal_year), 0), 1) AS yoy_pct
FROM rev
ORDER BY segment_code, fiscal_year;

-- Section 4 ------------------------------------------------------------------
-- Operating margin per segment per quarter (REVENUE - COGS - SGA - RD).
WITH p AS (
  SELECT fiscal_year, fiscal_quarter, segment_code, account_type, amount_usd
  FROM gold.fact_fpa_actuals
)
SELECT
  fiscal_year,
  fiscal_quarter,
  segment_code,
  ROUND(MAX(CASE WHEN account_type = 'REVENUE' THEN amount_usd END) / 1e6, 2)       AS revenue_mm,
  ROUND(MAX(CASE WHEN account_type = 'COGS'    THEN amount_usd END) / 1e6, 2)       AS cogs_mm,
  ROUND(MAX(CASE WHEN account_type = 'SGA'     THEN amount_usd END) / 1e6, 2)       AS sga_mm,
  ROUND(MAX(CASE WHEN account_type = 'RD'      THEN amount_usd END) / 1e6, 2)       AS rd_mm,
  ROUND((MAX(CASE WHEN account_type = 'REVENUE' THEN amount_usd END)
       - MAX(CASE WHEN account_type IN ('COGS','SGA','RD') THEN amount_usd END))
       / 1e6, 2) AS op_income_mm
FROM p
GROUP BY ALL
ORDER BY fiscal_year, fiscal_quarter, segment_code;
