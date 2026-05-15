-- ============================================================================
-- GOLD — dim_supplier
-- ============================================================================
-- Phase 2 hooks: canonical_supplier_id, entity_resolution_cluster_id.
-- Pre-Phase 2, canonical_supplier_id == supplier_id (identity).
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.dim_supplier
COMMENT "Supplier dim. ML hint columns surface category affinity + maverick propensity. Phase 2 entity-resolution model populates canonical_supplier_id."
AS
WITH ranked AS (
  SELECT
    supplier_id,
    supplier_name,
    country_code,
    region,
    language_code,
    created_date,
    category_primary,
    category_secondary_json,
    maverick_propensity,
    segment_affinity,
    ROW_NUMBER() OVER (PARTITION BY supplier_id
                       ORDER BY CASE WHEN supplier_name IS NOT NULL THEN 0 ELSE 1 END) AS rn
  FROM ${schema_silver}.supplier
)
SELECT
  supplier_id,
  supplier_name,
  country_code,
  region,
  language_code,
  created_date,
  category_primary,
  category_secondary_json,
  maverick_propensity,
  segment_affinity,
  supplier_id                                AS canonical_supplier_id,
  CAST(NULL AS STRING)                       AS entity_resolution_cluster_id
FROM ranked
WHERE rn = 1;
