-- ============================================================================
-- SPEND — exploration queries (redesigned PR → PO → invoice model)
-- ============================================================================
-- Three fact tables in the spend pillar:
--   gold.fact_purchase_requests  → Ariba PR intake (volume + cancel rate)
--   gold.fact_purchase_orders    → Fusion PO commitments (committed spend)
--   gold.fact_invoices           → Fusion AP invoices LINE grain (realized spend,
--                                  unit-of-truth for ML classification & tie-out)
--
-- Tie-out: fact_invoices.amount per (fy, fq, segment) ≈ anchor cogs+sga+rd ±2%.
-- ============================================================================

USE CATALOG horizontal_finance_dev;

-- Section 1 ------------------------------------------------------------------
-- Realized spend by segment × fiscal quarter (the headline number).
-- Ties back to _meta.dim_period_anchors.cogs + sga + rd within ±2%.
SELECT
  fiscal_year,
  fiscal_quarter,
  segment_code,
  ROUND(SUM(amount) / 1e6, 2)         AS spend_mm,
  COUNT(*)                            AS invoice_lines,
  COUNT(DISTINCT invoice_id)          AS invoices,
  COUNT(DISTINCT supplier_id)         AS suppliers
FROM gold.fact_invoices
GROUP BY ALL
ORDER BY fiscal_year, fiscal_quarter, segment_code;

-- Section 2a -----------------------------------------------------------------
-- Spend distribution across the 8 PARENT categories (executive rollup).
SELECT
  true_category_primary,
  COUNT(*)                       AS lines,
  ROUND(SUM(amount) / 1e6, 2)    AS spend_mm,
  ROUND(100.0 * SUM(amount) / SUM(SUM(amount)) OVER (), 1) AS pct_of_total,
  COUNT(DISTINCT supplier_id)    AS suppliers
FROM gold.fact_invoices
GROUP BY true_category_primary
ORDER BY spend_mm DESC;

-- Section 2b -----------------------------------------------------------------
-- Spend distribution across the 30 leaf categories (category-manager drill).
-- This is the label distribution the ML classifier learns at the leaf tier.
SELECT
  true_category_primary,
  true_category_secondary,
  COUNT(*)                       AS lines,
  ROUND(SUM(amount) / 1e6, 2)    AS spend_mm,
  ROUND(AVG(amount), 0)          AS avg_line_amount,
  COUNT(DISTINCT supplier_id)    AS suppliers
FROM gold.fact_invoices
GROUP BY true_category_primary, true_category_secondary
ORDER BY true_category_primary, spend_mm DESC;

-- Section 2c -----------------------------------------------------------------
-- Taxonomy reference — the source of truth for valid (primary, secondary) pairs.
SELECT
  primary_code,
  primary_name,
  COUNT(*)                                                          AS n_leaves,
  COLLECT_LIST(secondary_code)                                      AS leaves
FROM gold.dim_spend_category
GROUP BY primary_code, primary_name
ORDER BY n_leaves DESC, primary_code;

-- Section 3 ------------------------------------------------------------------
-- Direct vs. Indirect breakdown (rule-based off GL natural account).
-- Direct = COGS-bearing accounts; Indirect = SGA/RD/etc.
SELECT
  direct_indirect,
  COUNT(*)                       AS lines,
  ROUND(SUM(amount) / 1e6, 2)    AS spend_mm,
  ROUND(100.0 * SUM(amount) / SUM(SUM(amount)) OVER (), 1) AS pct_of_total
FROM gold.fact_invoices
GROUP BY direct_indirect
ORDER BY spend_mm DESC;

-- Section 4 ------------------------------------------------------------------
-- Addressable vs. Non-Addressable (sourcing scope).
-- Non-addressable = regulated supplier (~8%); sourcing can't move it.
SELECT
  addressability,
  COUNT(*)                       AS lines,
  ROUND(SUM(amount) / 1e6, 2)    AS spend_mm,
  ROUND(100.0 * SUM(amount) / SUM(SUM(amount)) OVER (), 1) AS pct_of_total,
  COUNT(DISTINCT supplier_id)    AS suppliers
FROM gold.fact_invoices
GROUP BY addressability
ORDER BY spend_mm DESC;

-- Section 5 ------------------------------------------------------------------
-- PR → PO → Invoice conversion funnel.
-- PR conversion = released / total (cancelled + released + open).
-- PO conversion = invoiced / total.
WITH pr_stats AS (
  SELECT
    fiscal_year,
    fiscal_quarter,
    COUNT(*)                                              AS pr_lines,
    SUM(CASE WHEN pr_status = 'released' THEN 1 ELSE 0 END) AS pr_released,
    SUM(CASE WHEN pr_status = 'cancelled' THEN 1 ELSE 0 END) AS pr_cancelled,
    ROUND(SUM(estimated_extended_amount) / 1e6, 2)        AS pr_estimated_mm
  FROM gold.fact_purchase_requests
  GROUP BY fiscal_year, fiscal_quarter
),
po_stats AS (
  SELECT
    fiscal_year,
    fiscal_quarter,
    COUNT(*)                                              AS po_lines,
    ROUND(SUM(extended_amount) / 1e6, 2)                  AS po_committed_mm
  FROM gold.fact_purchase_orders
  GROUP BY fiscal_year, fiscal_quarter
),
inv_stats AS (
  SELECT
    fiscal_year,
    fiscal_quarter,
    COUNT(*)                                              AS inv_lines,
    ROUND(SUM(amount) / 1e6, 2)                           AS inv_realized_mm
  FROM gold.fact_invoices
  GROUP BY fiscal_year, fiscal_quarter
)
SELECT
  COALESCE(pr_stats.fiscal_year, po_stats.fiscal_year, inv_stats.fiscal_year)         AS fiscal_year,
  COALESCE(pr_stats.fiscal_quarter, po_stats.fiscal_quarter, inv_stats.fiscal_quarter) AS fiscal_quarter,
  pr_stats.pr_lines,
  pr_stats.pr_released,
  pr_stats.pr_cancelled,
  pr_stats.pr_estimated_mm,
  po_stats.po_lines,
  po_stats.po_committed_mm,
  inv_stats.inv_lines,
  inv_stats.inv_realized_mm
FROM pr_stats
FULL OUTER JOIN po_stats  USING (fiscal_year, fiscal_quarter)
FULL OUTER JOIN inv_stats USING (fiscal_year, fiscal_quarter)
ORDER BY fiscal_year, fiscal_quarter;

-- Section 6 ------------------------------------------------------------------
-- Top 20 suppliers by realized spend.
SELECT
  fi.supplier_id,
  fi.supplier_name,
  fi.supplier_region,
  fi.supplier_country,
  fi.is_regulated_supplier,
  fi.supplier_maverick_propensity,
  ROUND(SUM(fi.amount) / 1e6, 2) AS spend_mm,
  COUNT(*)                       AS invoice_lines
FROM gold.fact_invoices fi
GROUP BY ALL
ORDER BY spend_mm DESC
LIMIT 20;

-- Section 7 ------------------------------------------------------------------
-- AP invoice match rate — PO-matched (3-way) vs. non-PO direct vouchers.
-- Non-PO is a managed-spend risk signal — purchases that skipped procurement.
SELECT
  po_matched_flag,
  fiscal_year,
  fiscal_quarter,
  COUNT(DISTINCT invoice_id)     AS invoices,
  ROUND(SUM(amount) / 1e6, 2)    AS amount_mm
FROM gold.fact_invoices
GROUP BY ALL
ORDER BY fiscal_year, fiscal_quarter, po_matched_flag;

-- Section 8 ------------------------------------------------------------------
-- AP ops: payment status distribution + on-time payment rate by quarter.
SELECT
  fiscal_year,
  fiscal_quarter,
  payment_status,
  COUNT(DISTINCT invoice_id)                                          AS invoices,
  ROUND(SUM(amount) / 1e6, 2)                                         AS amount_mm,
  ROUND(100.0 * AVG(CASE WHEN is_on_time_payment THEN 1.0
                         WHEN is_on_time_payment = FALSE THEN 0.0
                         ELSE NULL END), 1)                            AS on_time_pct,
  ROUND(AVG(days_to_pay), 1)                                          AS avg_days_to_pay
FROM gold.fact_invoices
GROUP BY ALL
ORDER BY fiscal_year, fiscal_quarter, payment_status;

-- Section 9 ------------------------------------------------------------------
-- Payment terms mix (Net15 / Net30 / Net45 / Net60) — supplier-level config.
SELECT
  payment_terms,
  COUNT(DISTINCT supplier_id)        AS suppliers,
  COUNT(DISTINCT invoice_id)         AS invoices,
  ROUND(SUM(amount) / 1e6, 2)        AS amount_mm,
  ROUND(100.0 * SUM(amount) / SUM(SUM(amount)) OVER (), 1) AS pct_of_spend
FROM gold.fact_invoices
GROUP BY payment_terms
ORDER BY amount_mm DESC;

-- Section 10 -----------------------------------------------------------------
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

-- Section 11 -----------------------------------------------------------------
-- Ariba → Fusion cross-system bridge: which released PRs flowed through to POs?
-- Joins fact_purchase_requests (released only) → fact_purchase_orders via
-- source_pr_number. Released PRs without a matching PO indicate processing lag.
SELECT
  pr.fiscal_year,
  pr.fiscal_quarter,
  pr.segment_code,
  COUNT(DISTINCT pr.pr_number)                                                 AS released_prs,
  COUNT(DISTINCT po.po_number)                                                 AS resulting_pos,
  ROUND(100.0 * COUNT(DISTINCT po.po_number) / NULLIF(COUNT(DISTINCT pr.pr_number), 0), 1)
                                                                               AS conversion_pct
FROM gold.fact_purchase_requests pr
LEFT JOIN gold.fact_purchase_orders po
  ON pr.pr_number = po.source_pr_number
WHERE pr.pr_status = 'released'
GROUP BY ALL
ORDER BY pr.fiscal_year, pr.fiscal_quarter, pr.segment_code;

-- Section 12 -----------------------------------------------------------------
-- ML predictions vs. ground truth (only meaningful after batch_inference runs).
-- Empty (or all NULL predicted_*) until the model has scored.
-- Parent-tier accuracy should be meaningfully higher than leaf-tier — that's
-- the headline "exec view" vs. "category-manager view" framing.
SELECT
  predicted_secondary_category IS NOT NULL                  AS has_prediction,
  COUNT(*)                                                  AS lines,
  ROUND(AVG(secondary_confidence), 3)                       AS avg_leaf_confidence,
  ROUND(AVG(primary_confidence), 3)                         AS avg_parent_confidence,
  ROUND(100.0 * AVG(CASE WHEN predicted_secondary_category = true_category_secondary
                         THEN 1.0 ELSE 0.0 END), 1)         AS leaf_accuracy_pct,
  ROUND(100.0 * AVG(CASE WHEN predicted_primary_category = true_category_primary
                         THEN 1.0 ELSE 0.0 END), 1)         AS parent_accuracy_pct
FROM gold.fact_invoices
GROUP BY has_prediction
ORDER BY has_prediction DESC;

-- Section 13 -----------------------------------------------------------------
-- Confusion at the parent tier — which parents do we mix up most?
-- Useful for the demo deck: "the model rarely confuses Direct Materials with
-- Professional Services, but it does confuse IT_Telecom with Software_Cloud."
SELECT
  true_category_primary                                     AS truth_parent,
  predicted_primary_category                                AS pred_parent,
  COUNT(*)                                                  AS lines,
  ROUND(SUM(amount) / 1e6, 2)                               AS spend_mm
FROM gold.fact_invoices
WHERE predicted_primary_category IS NOT NULL
  AND true_category_primary <> predicted_primary_category
GROUP BY ALL
ORDER BY spend_mm DESC
LIMIT 20;
