-- ============================================================================
-- BRONZE — SAP Ariba Contract Workspace (inbound / procurement contracts)
-- ============================================================================
-- Target schema: ${schema_bronze_ariba}
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_bronze_ariba}.ARIBA_CONTRACT_WORKSPACE
COMMENT "Ariba contract workspace (inbound contracts). TotalCommittedSpend vs ActualSpendToDate drives the Phase 2 contract-leakage detection."
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  _metadata.file_modification_time AS _ingested_at
FROM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/sap_ariba/ARIBA_CONTRACT_WORKSPACE.csv",
  format => "csv",
  header => true,
  inferColumnTypes => true
);
