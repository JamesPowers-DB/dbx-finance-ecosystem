-- ============================================================================
-- GOLD — dim_customer
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.dim_customer
COMMENT "Customer dim."
AS
SELECT
  customer_id,
  customer_name,
  country_code,
  region,
  primary_segment_code
FROM ${schema_silver}.customer;
