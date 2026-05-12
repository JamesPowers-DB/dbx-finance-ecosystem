-- ============================================================================
-- GOLD — fact_emp_quarterly_cost (derived from anchor headcount + avg salary)
-- ============================================================================
-- We don't (yet) have an HR generator. Demo headcount cost is derived from
-- _meta.dim_period_anchors.headcount_total per segment × an assumed average
-- fully-loaded quarterly cost ($45k/qtr ≈ $180k/yr loaded — typical for an
-- industrial conglomerate's blended cost profile).
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.fact_emp_quarterly_cost
COMMENT "Headcount-derived quarterly employee cost. Sourced from anchor headcount × $45k/quarter blended loaded cost assumption."
AS
SELECT
  a.fiscal_year,
  a.fiscal_quarter,
  a.segment_code,
  a.headcount_total                                              AS headcount,
  CAST(a.headcount_total * 45000.0 AS DECIMAL(18,2))             AS quarterly_cost_usd,
  CAST(45000.0 AS DECIMAL(18,2))                                 AS assumed_quarterly_cost_per_head
FROM ${catalog}.${schema_meta}.dim_period_anchors a
WHERE a.period_type = 'Q'
  AND a.segment_code <> 'CONSOL'
  AND a.headcount_total IS NOT NULL;
