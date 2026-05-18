-- ============================================================================
-- SILVER — supplier (canonical, source-tagged)
-- ============================================================================
-- Unions Ariba LFA1 + Fusion ap_supplier_sites_all. Pre-Phase 2,
-- supplier_canonical_id == supplier_id; entity-resolution will populate it.
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_silver}.supplier
COMMENT "Conformed supplier master. Reserves supplier_canonical_id for the Phase 2 entity-resolution model."
AS
WITH ariba_suppliers AS (
  SELECT
    'sap_ariba'                            AS source_system,
    'LFA1_SUPPLIER_MASTER'                 AS source_table,
    LIFNR                                  AS source_primary_key,
    LIFNR                                  AS supplier_id,
    NAME1                                  AS supplier_name,
    LAND1                                  AS country_code,
    CASE
      WHEN LAND1 IN ('US','CA','MX')                                  THEN 'NA'
      WHEN LAND1 IN ('DE','FR','GB','IT','ES','NL','BE','PL','CZ')    THEN 'EMEA'
      WHEN LAND1 IN ('CN','JP','IN','KR','AU','SG','TH')              THEN 'APAC'
      WHEN LAND1 IN ('BR','AR','CL','CO')                             THEN 'LATAM'
      ELSE 'OTHER'
    END                                    AS region,
    SPRAS                                  AS language_code,
    ERSDA                                  AS created_date,
    _supplier_category_primary             AS category_primary,
    _supplier_category_secondary_json      AS category_secondary_json,
    -- Bronze read_files() infers _maverick_propensity as STRING from CSV;
    -- cast to DOUBLE so downstream consumers (dim_supplier, fact_spend, ML feature prep)
    -- don't have to keep re-casting and don't hit BIGINT-unification errors in COALESCE.
    CAST(_maverick_propensity AS DOUBLE)   AS maverick_propensity,
    _industry_segment_affinity             AS segment_affinity,
    _payment_terms                         AS payment_terms,
    CAST(_is_regulated_flag AS BOOLEAN)    AS is_regulated_supplier
  FROM ${schema_bronze_ariba}.LFA1_SUPPLIER_MASTER
),
fusion_sites AS (
  SELECT
    'oracle_fusion'                                                   AS source_system,
    'ap_supplier_sites_all'                                           AS source_table,
    CAST(vendor_site_id AS STRING)                                    AS source_primary_key,
    vendor_id_ext                                                     AS supplier_id,
    NULL                                                              AS supplier_name,
    country                                                           AS country_code,
    CASE
      WHEN country IN ('US','CA','MX')                                THEN 'NA'
      WHEN country IN ('DE','FR','GB','IT','ES','NL','BE','PL','CZ')  THEN 'EMEA'
      WHEN country IN ('CN','JP','IN','KR','AU','SG','TH')            THEN 'APAC'
      WHEN country IN ('BR','AR','CL','CO')                           THEN 'LATAM'
      ELSE 'OTHER'
    END                                                               AS region,
    NULL                                                              AS language_code,
    NULL                                                              AS created_date,
    CAST(NULL AS STRING)                                              AS category_primary,
    CAST(NULL AS STRING)                                              AS category_secondary_json,
    -- Match Ariba side's DOUBLE type for the UNION ALL.
    CAST(NULL AS DOUBLE)                                              AS maverick_propensity,
    CAST(NULL AS STRING)                                              AS segment_affinity,
    CAST(NULL AS STRING)                                              AS payment_terms,
    CAST(NULL AS BOOLEAN)                                             AS is_regulated_supplier
  FROM ${schema_bronze_fusion}.ap_supplier_sites_all
  WHERE purchasing_site_flag = 'Y'
)
SELECT
  a.*,
  -- Phase 2 hooks (populated by supplier entity resolution model)
  CAST(NULL AS STRING) AS supplier_canonical_id,
  CAST(NULL AS STRING) AS entity_resolution_cluster_id
FROM (
  SELECT * FROM ariba_suppliers
  UNION ALL
  SELECT * FROM fusion_sites
) a;
