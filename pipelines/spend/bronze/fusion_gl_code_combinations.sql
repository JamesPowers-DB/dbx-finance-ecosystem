-- ============================================================================
-- BRONZE — Oracle Fusion chart of accounts (code combinations)
-- ============================================================================
-- Target schema: ${schema}
-- Relocated out of the (dropped) accounting pillar: fact_invoices joins this to
-- derive direct/indirect + addressability. It is the ONLY accounting-GL table
-- the lean spend-analytics fork retains.
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema}.bronze_gl_code_combinations
COMMENT "7-segment chart of accounts. Maps cost centers → entities → segments → natural accounts; supplies the direct/indirect + addressability flags on fact_invoices."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM read_files(
  "/Volumes/${catalog}/${schema}/${raw_volume}/oracle_fusion/gl_code_combinations.csv",
  format => "csv", header => true, inferColumnTypes => true);
