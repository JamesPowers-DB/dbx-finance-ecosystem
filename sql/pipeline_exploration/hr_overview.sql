-- ============================================================================
-- HR — headcount + employee cost exploration
-- ============================================================================
-- Today employee cost is derived from anchor headcount × $45k/quarter blended
-- loaded-cost assumption (see pipelines/hr/gold/fact_emp_quarterly_cost.sql).
-- Real HR feed lands later.
-- ============================================================================
USE CATALOG horizontal_finance_dev;

-- Section 1 ------------------------------------------------------------------
-- Quarterly headcount cost by segment.
SELECT
  fiscal_year,
  fiscal_quarter,
  segment_code,
  headcount,
  ROUND(quarterly_cost_usd / 1e6, 2)   AS quarterly_cost_mm
FROM gold.fact_emp_quarterly_cost
ORDER BY fiscal_year, fiscal_quarter, segment_code;

-- Section 2 ------------------------------------------------------------------
-- Headcount + cost trend across all quarters per segment.
SELECT
  segment_code,
  COUNT(*)                              AS quarters_observed,
  MIN(fiscal_year * 10 + fiscal_quarter) AS first_fyq,
  MAX(fiscal_year * 10 + fiscal_quarter) AS last_fyq,
  MIN(headcount)                        AS min_headcount,
  MAX(headcount)                        AS max_headcount,
  ROUND(AVG(headcount), 0)              AS avg_headcount,
  ROUND(SUM(quarterly_cost_usd) / 1e6, 2) AS total_cost_mm
FROM gold.fact_emp_quarterly_cost
GROUP BY segment_code
ORDER BY total_cost_mm DESC;

-- Section 3 ------------------------------------------------------------------
-- QoQ headcount change per segment (early signal for restructuring).
SELECT
  fiscal_year,
  fiscal_quarter,
  segment_code,
  headcount,
  LAG(headcount) OVER (PARTITION BY segment_code ORDER BY fiscal_year, fiscal_quarter) AS prior_qtr_headcount,
  headcount - LAG(headcount) OVER (PARTITION BY segment_code ORDER BY fiscal_year, fiscal_quarter) AS delta,
  ROUND(100.0 * (headcount - LAG(headcount) OVER (PARTITION BY segment_code ORDER BY fiscal_year, fiscal_quarter))
                / NULLIF(LAG(headcount) OVER (PARTITION BY segment_code ORDER BY fiscal_year, fiscal_quarter), 0), 2) AS pct_change
FROM gold.fact_emp_quarterly_cost
ORDER BY segment_code, fiscal_year, fiscal_quarter;
