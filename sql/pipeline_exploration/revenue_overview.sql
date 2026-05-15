-- ============================================================================
-- REVENUE — exploration queries
-- ============================================================================
USE CATALOG horizontal_finance_dev;

-- Section 1 ------------------------------------------------------------------
-- Total revenue by segment × fiscal quarter. Ties to _meta.dim_period_anchors.revenue ±2%.
SELECT
  fiscal_year,
  fiscal_quarter,
  segment_code,
  ROUND(SUM(amount) / 1e6, 2)        AS revenue_mm,
  COUNT(*)                           AS billing_events,
  COUNT(DISTINCT customer_id)        AS customers,
  COUNT(DISTINCT contract_id)        AS contracts
FROM gold.fact_revenue
GROUP BY ALL
ORDER BY fiscal_year, fiscal_quarter, segment_code;

-- Section 2 ------------------------------------------------------------------
-- Top 20 customers by revenue.
SELECT
  c.customer_id,
  c.customer_name,
  c.region,
  c.primary_segment_code,
  ROUND(SUM(fr.amount) / 1e6, 2)      AS revenue_mm,
  COUNT(DISTINCT fr.contract_id)      AS contracts,
  COUNT(*)                            AS billing_events
FROM gold.fact_revenue fr
LEFT JOIN gold.dim_customer c USING (customer_id)
GROUP BY ALL
ORDER BY revenue_mm DESC
LIMIT 20;

-- Section 3 ------------------------------------------------------------------
-- Billing status distribution — paid / billed / scheduled.
SELECT
  status,
  fiscal_year,
  fiscal_quarter,
  COUNT(*)                          AS events,
  ROUND(SUM(amount) / 1e6, 2)       AS amount_mm
FROM gold.fact_revenue
GROUP BY ALL
ORDER BY fiscal_year, fiscal_quarter, status;

-- Section 4 ------------------------------------------------------------------
-- Contract value distribution by Helios segment (outbound / commercial contracts).
SELECT
  segment_code,
  status,
  COUNT(*)                                       AS contracts,
  ROUND(SUM(effective_contract_value) / 1e6, 2)  AS total_value_mm,
  ROUND(AVG(effective_contract_value) / 1e3, 1)  AS avg_value_k,
  ROUND(PERCENTILE_APPROX(effective_contract_value, 0.50) / 1e3, 1) AS p50_value_k,
  ROUND(PERCENTILE_APPROX(effective_contract_value, 0.95) / 1e3, 1) AS p95_value_k
FROM silver.contract_outbound
GROUP BY ALL
ORDER BY segment_code, status;

-- Section 5 ------------------------------------------------------------------
-- Currency mix on outbound revenue — useful for FX exposure conversations.
SELECT
  currency,
  COUNT(*)                          AS events,
  ROUND(SUM(amount) / 1e6, 2)       AS revenue_mm,
  ROUND(100.0 * SUM(amount) / SUM(SUM(amount)) OVER (), 1) AS pct_of_revenue
FROM gold.fact_revenue
GROUP BY currency
ORDER BY revenue_mm DESC;

-- Section 6 ------------------------------------------------------------------
-- AR invoice flow — count + total by status per quarter.
SELECT
  fiscal_year,
  fiscal_quarter,
  status,
  COUNT(*)                          AS invoices,
  ROUND(SUM(total_amount) / 1e6, 2) AS amount_mm
FROM silver.invoice_ar
GROUP BY ALL
ORDER BY fiscal_year, fiscal_quarter, status;
