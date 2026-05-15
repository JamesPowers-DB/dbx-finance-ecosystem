-- ============================================================================
-- GOLD — dim_cost_center
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.dim_cost_center
COMMENT "Cost center dim derived from COA segment2. One row per (cost_center_code × segment)."
AS
SELECT DISTINCT
  cost_center_code,
  segment_code,
  entity_code,
  CONCAT(segment_code, '-', cost_center_code) AS cost_center_key
FROM ${schema_silver}.coa_account
WHERE cost_center_code IS NOT NULL;
