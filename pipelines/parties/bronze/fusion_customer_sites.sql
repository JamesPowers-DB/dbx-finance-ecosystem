-- ============================================================================
-- BRONZE — Oracle Fusion customer sites (address-level customer data)
-- ============================================================================
-- Target schema: ${schema_bronze_fusion}
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_bronze_fusion}.ar_customer_sites_all
COMMENT "Oracle Receivables customer sites. Bill-to / ship-to addresses for customer-side analytics."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/ar_customer_sites_all.csv",
  format => "csv", header => true, inferColumnTypes => true);
