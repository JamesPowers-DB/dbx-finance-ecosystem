-- ============================================================================
-- PARTIES — supplier + customer exploration queries
-- ============================================================================
USE CATALOG horizontal_finance_dev;

-- Section 1 ------------------------------------------------------------------
-- Supplier counts by region × primary spend category.
SELECT
  region,
  category_primary,
  COUNT(*)                  AS suppliers,
  ROUND(AVG(maverick_propensity), 3) AS avg_maverick
FROM gold.dim_supplier
WHERE category_primary IS NOT NULL
GROUP BY ALL
ORDER BY region, suppliers DESC;

-- Section 2 ------------------------------------------------------------------
-- Maverick supplier distribution — how many suppliers fall in each propensity bin?
SELECT
  CASE
    WHEN maverick_propensity < 0.05 THEN '00-05 (clean)'
    WHEN maverick_propensity < 0.10 THEN '05-10'
    WHEN maverick_propensity < 0.15 THEN '10-15'
    WHEN maverick_propensity < 0.20 THEN '15-20 (eval slice)'
    WHEN maverick_propensity < 0.25 THEN '20-25'
    ELSE '25+ (very maverick)'
  END                       AS maverick_bin,
  COUNT(*)                  AS suppliers,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct
FROM gold.dim_supplier
WHERE maverick_propensity IS NOT NULL
GROUP BY ALL
ORDER BY maverick_bin;

-- Section 3 ------------------------------------------------------------------
-- Top 25 suppliers by spend across all periods.
SELECT
  s.supplier_id,
  s.supplier_name,
  s.region,
  s.country_code,
  s.category_primary,
  s.maverick_propensity,
  ROUND(SUM(fi.amount) / 1e6, 2)           AS spend_mm,
  COUNT(DISTINCT fi.invoice_id)            AS invoices,
  COUNT(DISTINCT (fi.fiscal_year * 10 + fi.fiscal_quarter)) AS active_quarters
FROM gold.fact_invoices fi
LEFT JOIN gold.dim_supplier s USING (supplier_id)
GROUP BY ALL
ORDER BY spend_mm DESC
LIMIT 25;

-- Section 4 ------------------------------------------------------------------
-- Customer counts by region × primary segment.
SELECT
  region,
  primary_segment_code,
  COUNT(*)                  AS customers
FROM gold.dim_customer
WHERE primary_segment_code IS NOT NULL
GROUP BY ALL
ORDER BY region, customers DESC;

-- Section 5 ------------------------------------------------------------------
-- Top 25 customers by revenue.
SELECT
  c.customer_id,
  c.customer_name,
  c.region,
  c.primary_segment_code,
  ROUND(SUM(fr.amount) / 1e6, 2)         AS revenue_mm,
  COUNT(DISTINCT fr.contract_id)         AS contracts,
  COUNT(DISTINCT (fr.fiscal_year * 10 + fr.fiscal_quarter)) AS active_quarters
FROM gold.fact_revenue fr
LEFT JOIN gold.dim_customer c USING (customer_id)
GROUP BY ALL
ORDER BY revenue_mm DESC
LIMIT 25;

-- Section 6 ------------------------------------------------------------------
-- Supplier scorecard summary (Ariba supplier performance bronze).
SELECT
  EvaluationQuarter,
  ROUND(AVG(OnTimeDeliveryPct), 1)   AS avg_ontime_pct,
  ROUND(AVG(QualityScore), 2)        AS avg_quality,
  ROUND(AVG(ResponsivenessScore), 2) AS avg_responsiveness,
  ROUND(AVG(OverallRating), 2)       AS avg_overall,
  COUNT(*)                           AS suppliers_scored
FROM bronze_ariba.ARIBA_SUPPLIER_PERFORMANCE
GROUP BY EvaluationQuarter
ORDER BY EvaluationQuarter;
