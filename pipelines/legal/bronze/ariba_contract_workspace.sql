-- ============================================================================
-- BRONZE — SAP Ariba Contract Workspace (inbound / procurement contracts)
-- ============================================================================
-- Target schema: ${schema}
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema}.bronze_ariba_contract_workspace
COMMENT "Ariba contract workspace (inbound contracts). TotalCommittedSpend vs ActualSpendToDate drives the Phase 2 contract-leakage detection."
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  _metadata.file_modification_time AS _ingested_at
FROM read_files(
  "/Volumes/${catalog}/${schema}/${raw_volume}/sap_ariba/ARIBA_CONTRACT_WORKSPACE.csv",
  format => "csv",
  header => true,
  inferColumnTypes => true
);
