-- ============================================================================
-- REFERENCE — shared dimensions (date, segment, macro environment)
-- ============================================================================
USE CATALOG horizontal_finance_dev;

-- Section 1 ------------------------------------------------------------------
-- Calendar dim sanity — date range, total days, fiscal year breakdown.
SELECT
  MIN(date_key)                     AS earliest_date,
  MAX(date_key)                     AS latest_date,
  COUNT(*)                          AS total_days,
  COUNT(DISTINCT fiscal_year)       AS fiscal_years_covered,
  SUM(CASE WHEN is_weekend THEN 1 ELSE 0 END) AS weekend_days
FROM gold.dim_date;

-- Section 2 ------------------------------------------------------------------
-- Days per fiscal year × quarter (should be ~91 each).
SELECT
  fiscal_year,
  fiscal_quarter,
  COUNT(*)              AS days,
  MIN(date_key)         AS quarter_start,
  MAX(date_key)         AS quarter_end
FROM gold.dim_date
GROUP BY ALL
ORDER BY fiscal_year, fiscal_quarter;

-- Section 3 ------------------------------------------------------------------
-- Segment dim — current state.
SELECT * FROM gold.dim_segment ORDER BY sort_order;

-- Section 4 ------------------------------------------------------------------
-- Macro environment — most recent 18 months. Shows the hand-engineered narrative arc:
-- 2024H2 trough → 2025H1 recovery → 2025H2 rebound → 2026 moderation.
SELECT
  period_month,
  ROUND(gdp_growth_idx, 3)            AS gdp,
  ROUND(inflation_idx, 3)             AS inflation,
  ROUND(demand_idx_sales, 3)          AS demand_sales,
  ROUND(demand_idx_mfg, 3)            AS demand_mfg,
  ROUND(supply_chain_stress_idx, 3)   AS supply_stress,
  ROUND(seasonality_idx, 3)           AS seasonality
FROM gold.dim_macro_environment
WHERE period_month >= ADD_MONTHS(current_date(), -18)
ORDER BY period_month;

-- Section 5 ------------------------------------------------------------------
-- Quarterly averages of macro indices for a smoother view of the arc.
SELECT
  YEAR(period_month)                          AS yr,
  QUARTER(period_month)                       AS qtr,
  ROUND(AVG(gdp_growth_idx), 3)               AS gdp,
  ROUND(AVG(inflation_idx), 3)                AS inflation,
  ROUND(AVG(demand_idx_sales), 3)             AS demand_sales,
  ROUND(AVG(demand_idx_mfg), 3)               AS demand_mfg,
  ROUND(AVG(supply_chain_stress_idx), 3)      AS supply_stress
FROM gold.dim_macro_environment
GROUP BY ALL
ORDER BY yr, qtr;
