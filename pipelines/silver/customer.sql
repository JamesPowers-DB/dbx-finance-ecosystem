-- ============================================================================
-- SILVER — customer (canonical)
-- ============================================================================
-- Derived from Fusion ar_customer_sites_all (addresses) joined to CMS
-- contract_party (segment/industry hints from contracts).
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_silver}.customer
COMMENT "Conformed customer master."
AS
WITH from_fusion AS (
  SELECT
    cust_account_id_ext                            AS customer_id,
    FIRST(customer_name)                           AS customer_name,
    FIRST(country)                                 AS country_code,
    CASE
      WHEN FIRST(country) IN ('US','CA','MX')                                 THEN 'NA'
      WHEN FIRST(country) IN ('DE','FR','GB','IT','ES','NL','BE','PL','CZ')   THEN 'EMEA'
      WHEN FIRST(country) IN ('CN','JP','IN','KR','AU','SG','TH')             THEN 'APAC'
      WHEN FIRST(country) IN ('BR','AR','CL','CO')                            THEN 'LATAM'
      ELSE 'OTHER'
    END                                            AS region
  FROM ${schema_bronze_fusion}.ar_customer_sites_all
  GROUP BY cust_account_id_ext
),
contract_segments AS (
  SELECT
    p.party_id                                     AS customer_id,
    FIRST(c.helios_entity_segment)                 AS primary_segment_code
  FROM ${schema_bronze_cms}.contract_party p
  JOIN ${schema_bronze_cms}.contract c
    ON p.contract_id = c.contract_id
  WHERE p.party_role = 'Customer'
  GROUP BY p.party_id
)
SELECT
  'oracle_fusion'                AS source_system,
  'ar_customer_sites_all+cms'    AS source_table,
  f.customer_id                  AS source_primary_key,
  f.customer_id,
  f.customer_name,
  f.country_code,
  f.region,
  cs.primary_segment_code
FROM from_fusion f
LEFT JOIN contract_segments cs USING (customer_id);
