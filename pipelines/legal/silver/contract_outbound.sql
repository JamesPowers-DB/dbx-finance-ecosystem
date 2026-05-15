-- ============================================================================
-- SILVER — contract_outbound (commercial / revenue-side contracts from CMS)
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_silver}.contract_outbound
COMMENT "Outbound commercial contract headers with amendment-adjusted value."
AS
WITH amend_totals AS (
  SELECT contract_id, SUM(value_delta) AS amendment_value_delta
  FROM ${schema_bronze_cms}.contract_amendment
  GROUP BY contract_id
)
SELECT
  'inhouse_cms'                       AS source_system,
  'contract'                          AS source_table,
  c.contract_id                       AS source_primary_key,
  c.contract_id,
  c.contract_number,
  c.customer_id,
  c.helios_entity_segment             AS segment_code,
  CAST(c.signed_date AS DATE)         AS signed_date,
  CAST(c.start_date AS DATE)          AS start_date,
  CAST(c.end_date AS DATE)            AS end_date,
  CAST(c.total_contract_value AS DECIMAL(18,2))                                 AS total_contract_value,
  CAST(COALESCE(a.amendment_value_delta, 0) AS DECIMAL(18,2))                   AS amendment_value_delta,
  CAST(c.total_contract_value + COALESCE(a.amendment_value_delta, 0) AS DECIMAL(18,2)) AS effective_contract_value,
  c.currency,
  c.status,
  c.commercial_terms,
  c.governing_law
FROM ${schema_bronze_cms}.contract c
LEFT JOIN amend_totals a USING (contract_id);
