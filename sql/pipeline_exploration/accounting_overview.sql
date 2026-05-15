-- ============================================================================
-- ACCOUNTING — exploration queries
-- ============================================================================
USE CATALOG horizontal_finance_dev;

-- Section 1 ------------------------------------------------------------------
-- Journal entry volume by source per period. Payables and Receivables
-- should dominate; Manual / Recurring should be a smaller share.
SELECT
  period_name,
  je_source,
  COUNT(*)                          AS je_headers
FROM silver.gl_journal_header
GROUP BY ALL
ORDER BY period_name, je_source;

-- Section 2 ------------------------------------------------------------------
-- Per-JE balance check — Σ(dr) − Σ(cr) should be exactly 0 per je_header_id.
-- This is the strict-balance invariant we enforced in reconcile.py.
SELECT
  COUNT(*)                                                AS total_jes,
  SUM(CASE WHEN ABS(net_dr_cr) > 0.01 THEN 1 ELSE 0 END)  AS unbalanced_jes,
  MAX(ABS(net_dr_cr))                                     AS worst_imbalance
FROM (
  SELECT je_header_id, SUM(accounted_dr - accounted_cr) AS net_dr_cr
  FROM silver.gl_journal_line
  GROUP BY je_header_id
);

-- Section 3 ------------------------------------------------------------------
-- Trial balance summary for the most recent period × segment × account type.
-- Use this to sanity-check the GL totals vs. spend / revenue facts.
WITH latest AS (
  SELECT MAX(period_name) AS p FROM silver.gl_journal_header
)
SELECT
  fge.period_name,
  fge.segment_code,
  fge.account_type,
  COUNT(*)                                  AS lines,
  ROUND(SUM(fge.accounted_dr) / 1e6, 2)     AS dr_mm,
  ROUND(SUM(fge.accounted_cr) / 1e6, 2)     AS cr_mm,
  ROUND(SUM(fge.net_amount) / 1e6, 2)       AS net_mm
FROM gold.fact_gl_entries fge, latest
WHERE fge.period_name = latest.p
  AND fge.account_type IS NOT NULL
GROUP BY ALL
ORDER BY fge.segment_code, fge.account_type;

-- Section 4 ------------------------------------------------------------------
-- Chart of accounts — how many active code combinations per (segment, account_type).
SELECT
  segment_code,
  account_type,
  COUNT(*)                            AS code_combinations,
  COUNT(DISTINCT cost_center_code)    AS cost_centers,
  COUNT(DISTINCT natural_account_code) AS natural_accounts
FROM silver.coa_account
WHERE enabled_flag = 'Y'
GROUP BY ALL
ORDER BY segment_code, account_type;

-- Section 5 ------------------------------------------------------------------
-- Account-type spend across all periods (period_net is debit-positive for
-- expense accounts, credit-positive for revenue accounts).
SELECT
  account_type,
  COUNT(DISTINCT period_name)         AS periods,
  ROUND(SUM(period_dr) / 1e6, 2)      AS period_dr_mm,
  ROUND(SUM(period_cr) / 1e6, 2)      AS period_cr_mm,
  ROUND(SUM(period_net) / 1e6, 2)     AS period_net_mm
FROM gold.fact_trial_balance
WHERE account_type IS NOT NULL
GROUP BY account_type
ORDER BY ABS(SUM(period_net)) DESC;

-- Section 6 ------------------------------------------------------------------
-- Top 15 natural accounts by activity.
SELECT
  da.account_code,
  da.account_description,
  da.account_type,
  COUNT(*)                                      AS entries,
  ROUND(SUM(fge.accounted_dr) / 1e6, 2)         AS total_dr_mm
FROM gold.fact_gl_entries fge
LEFT JOIN gold.dim_account da
  ON fge.natural_account_code = da.account_code
GROUP BY ALL
ORDER BY entries DESC
LIMIT 15;
