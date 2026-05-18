-- ============================================================================
-- LEGAL — contract exploration queries (inbound + outbound)
-- ============================================================================
USE CATALOG horizontal_finance_dev;

-- Section 1 ------------------------------------------------------------------
-- Active commercial contracts (outbound / revenue-side) by segment.
SELECT
  segment_code,
  status,
  COUNT(*)                                            AS contracts,
  ROUND(SUM(effective_contract_value) / 1e6, 2)       AS total_value_mm,
  ROUND(AVG(effective_contract_value) / 1e3, 1)       AS avg_value_k,
  MIN(start_date)                                     AS earliest_start,
  MAX(end_date)                                       AS latest_end
FROM silver.contract_outbound
GROUP BY ALL
ORDER BY segment_code, status;

-- Section 2 ------------------------------------------------------------------
-- Inbound contracts (procurement-side / Ariba) by contract type + region.
SELECT
  contract_type,
  region,
  status,
  COUNT(*)                                            AS contracts,
  ROUND(SUM(total_committed_spend) / 1e6, 2)          AS committed_mm,
  ROUND(SUM(actual_spend_to_date) / 1e6, 2)           AS actual_mm,
  ROUND(100.0 * SUM(actual_spend_to_date) /
                NULLIF(SUM(total_committed_spend), 0), 1) AS utilization_pct
FROM silver.contract_inbound
GROUP BY ALL
ORDER BY contract_type, region;

-- Section 3 ------------------------------------------------------------------
-- Contract amendments — frequency by year.
SELECT
  YEAR(CAST(effective_date AS DATE))   AS amendment_year,
  amendment_type,
  COUNT(*)                              AS amendments,
  ROUND(SUM(value_delta) / 1e6, 2)      AS value_delta_mm
FROM bronze_cms.contract_amendment
GROUP BY ALL
ORDER BY amendment_year, amendment_type;

-- Section 4 ------------------------------------------------------------------
-- Contract expiration calendar — upcoming 12 months of outbound contract endings.
SELECT
  DATE_TRUNC('MONTH', end_date)         AS expiration_month,
  segment_code,
  COUNT(*)                              AS contracts_expiring,
  ROUND(SUM(effective_contract_value) / 1e6, 2) AS expiring_value_mm
FROM silver.contract_outbound
WHERE end_date BETWEEN current_date() AND current_date() + INTERVAL 12 MONTH
GROUP BY ALL
ORDER BY expiration_month, segment_code;

-- Section 5 ------------------------------------------------------------------
-- Payment terms distribution on outbound contracts (Net 30 / Net 45 / etc).
SELECT
  commercial_terms,
  COUNT(*)                                            AS contracts,
  ROUND(SUM(effective_contract_value) / 1e6, 2)       AS total_value_mm,
  ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 1)  AS pct_of_contracts
FROM silver.contract_outbound
GROUP BY commercial_terms
ORDER BY contracts DESC;

-- Section 6 ------------------------------------------------------------------
-- Off-contract spend opportunity — supplier-quarter combos where there's
-- AP spend but no active inbound contract covering them. (Phase 2 leakage
-- detection candidates.)
SELECT
  fi.segment_code,
  fi.fiscal_year,
  fi.fiscal_quarter,
  COUNT(*)                                    AS invoice_lines,
  ROUND(SUM(fi.amount) / 1e6, 2)              AS off_contract_mm
FROM gold.fact_invoices fi
LEFT JOIN silver.contract_inbound ci
  ON fi.supplier_id = ci.supplier_id
 AND ci.status = 'Active'
WHERE ci.contract_workspace_id IS NULL
GROUP BY ALL
ORDER BY off_contract_mm DESC
LIMIT 20;
