-- ============================================================================
-- BRONZE — Oracle Fusion supplier sites (address-level vendor data)
-- ============================================================================
-- Target schema: ${schema}
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema}.bronze_ap_supplier_sites_all
COMMENT "Oracle Payables supplier sites. Address-level data for supplier entity resolution (Phase 2 ML)."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM read_files(
  "/Volumes/${catalog}/${schema}/${raw_volume}/oracle_fusion/ap_supplier_sites_all.csv",
  format => "csv", header => true, inferColumnTypes => true);
