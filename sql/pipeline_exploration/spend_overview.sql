-- ============================================================================
-- SPEND — exploration queries
-- ============================================================================
-- Run in the Databricks SQL editor. Adjust the USE CATALOG line if your
-- bundle deployed to a different name.
-- ============================================================================

USE CATALOG horizontal_finance_dev;

-- Section 1 ------------------------------------------------------------------
-- Total spend by segment × fiscal quarter (the headline number).
-- Should tie back to _meta.dim_period_anchors.cogs + sga + rd within ±2%.
SELECT
  fiscal_year,
  fiscal_quarter,
  segment_code,
  ROUND(SUM(extended_amount) / 1e6, 2) AS spend_mm,
  COUNT(*)                             AS po_lines,
  COUNT(DISTINCT po_number)            AS pos,
  COUNT(DISTINCT supplier_id)          AS suppliers
FROM gold.fact_spend
GROUP BY ALL
ORDER BY fiscal_year, fiscal_quarter, segment_code;

-- Section 2 ------------------------------------------------------------------
-- Spend distribution across the 30 ground-truth categories.
-- This is the label distribution the ML model is trying to predict.
SELECT
  true_spend_category,
  COUNT(*)                                  AS lines,
  ROUND(SUM(extended_amount) / 1e6, 2)      AS spend_mm,
  ROUND(AVG(extended_amount), 0)            AS avg_line_amount,
  COUNT(DISTINCT supplier_id)               AS suppliers
FROM gold.fact_spend
GROUP BY true_spend_category
ORDER BY spend_mm DESC;

-- Section 3 ------------------------------------------------------------------
-- Top 20 suppliers by spend across all periods.
SELECT
  s.supplier_id,
  s.supplier_name,
  s.region,
  s.category_primary               AS category_primary_hint,
  s.maverick_propensity,
  ROUND(SUM(fs.extended_amount) / 1e6, 2) AS spend_mm,
  COUNT(*)                                AS po_lines
FROM gold.fact_spend fs
LEFT JOIN gold.dim_supplier s USING (supplier_id)
GROUP BY ALL
ORDER BY spend_mm DESC
LIMIT 20;

-- Section 4 ------------------------------------------------------------------
-- PO document type breakdown — what mix of NB / FO / K / ZUB are we seeing?
SELECT
  po_doc_type,
  COUNT(*)                                 AS lines,
  ROUND(SUM(extended_amount) / 1e6, 2)     AS spend_mm,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1) AS pct_of_lines
FROM gold.fact_spend
GROUP BY po_doc_type
ORDER BY lines DESC;

-- Section 5 ------------------------------------------------------------------
-- AP invoice match rate — how many invoices have a matching PO (3-way match)
-- vs. direct vouchers (non-PO spend, which is a managed-spend risk signal).
SELECT
  po_matched_flag,
  fiscal_year,
  fiscal_quarter,
  COUNT(*)                            AS invoices,
  ROUND(SUM(gross_amount) / 1e6, 2)   AS gross_mm
FROM silver.invoice_ap
GROUP BY ALL
ORDER BY fiscal_year, fiscal_quarter, po_matched_flag;

-- Section 6 ------------------------------------------------------------------
-- Sourcing event throughput — award rate by quarter.
SELECT
  fiscal_year,
  fiscal_quarter,
  event_type,
  COUNT(*)                                            AS events,
  ROUND(AVG(suppliers_invited), 1)                    AS avg_invited,
  ROUND(AVG(suppliers_responded * 1.0 / NULLIF(suppliers_invited, 0)) * 100, 1) AS response_pct,
  ROUND(SUM(awarded_amount) / 1e6, 2)                 AS awarded_mm
FROM silver.sourcing_event
GROUP BY ALL
ORDER BY fiscal_year, fiscal_quarter, event_type;

-- Section 7 ------------------------------------------------------------------
-- "Maverick" spend — purchases from suppliers whose primary category
-- doesn't match the actual PO line category. These are the hard cases
-- the ML model is trained to identify.
SELECT
  fs.segment_code,
  fs.true_spend_category,
  COUNT(*)                                AS maverick_lines,
  ROUND(SUM(fs.extended_amount) / 1e6, 2) AS maverick_mm
FROM gold.fact_spend fs
LEFT JOIN gold.dim_supplier s USING (supplier_id)
WHERE s.category_primary IS NOT NULL
  AND s.category_primary <> fs.true_spend_category
GROUP BY ALL
ORDER BY maverick_mm DESC
LIMIT 20;
