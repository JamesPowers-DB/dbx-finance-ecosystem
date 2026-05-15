-- ============================================================================
-- GOLD — fact_emp_quarterly_cost (derived from dim_employees SCD2 snapshots)
-- ============================================================================
-- Aggregates active employees as of each quarter-end (per row in
-- _meta.dim_period_anchors) by segment, summing their quarterly loaded cost.
--
-- The grain is (fiscal_year, fiscal_quarter, segment_code). One row per active
-- segment per anchor period. Terminated employees are excluded.
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.fact_emp_quarterly_cost
COMMENT "Quarterly employee cost aggregated from gold.dim_employees at each (fiscal_year, fiscal_quarter) quarter-end. Excludes terminated workers."
AS
WITH quarter_ends AS (
  SELECT DISTINCT
    fiscal_year,
    fiscal_quarter,
    CASE fiscal_quarter
      WHEN 1 THEN MAKE_DATE(fiscal_year, 3, 31)
      WHEN 2 THEN MAKE_DATE(fiscal_year, 6, 30)
      WHEN 3 THEN MAKE_DATE(fiscal_year, 9, 30)
      WHEN 4 THEN MAKE_DATE(fiscal_year, 12, 31)
    END AS quarter_end_date
  FROM ${catalog}.${schema_meta}.dim_period_anchors
  WHERE period_type = 'Q'
)
SELECT
  qe.fiscal_year,
  qe.fiscal_quarter,
  e.segment_code,
  COUNT(DISTINCT e.employee_id)                          AS headcount,
  CAST(SUM(e.quarterly_loaded_cost_usd) AS DECIMAL(18, 2)) AS quarterly_cost_usd,
  CAST(AVG(e.quarterly_loaded_cost_usd) AS DECIMAL(18, 2)) AS avg_quarterly_cost_per_head
FROM ${schema_gold}.dim_employees e
JOIN quarter_ends qe
  ON qe.quarter_end_date >= e.effective_from
 AND qe.quarter_end_date <  e.effective_to
WHERE e.employment_status = 'active'
GROUP BY qe.fiscal_year, qe.fiscal_quarter, e.segment_code;
