-- ============================================================================
-- BRONZE — SAP Ariba Purchase Requests (EBAN)
-- ============================================================================
-- Target schema: ${schema_bronze_ariba}
-- Reads files from: /Volumes/${catalog}/${schema_raw}/${raw_volume}/sap_ariba/
--
-- EBAN status codes (real SAP):
--   B = Released  → flows to Fusion as a PO
--   L = Cancelled
--   N = Open (not yet processed)
-- ============================================================================

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_ariba}.EBAN_PR_HEADER
COMMENT "SAP Purchase Requisition header (EBAN). One row per PR. STATU = 'B' means released — those flow downstream to Fusion as POs."
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/sap_ariba/EBAN_PR_HEADER_*.csv",
  format => "csv",
  header => true,
  inferColumnTypes => true
);

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_ariba}.EBAN_PR_LINE
COMMENT "SAP Purchase Requisition line (EBAN). Carries the line description TXZ01, estimated PREIS, and the 2-tier _true_category_primary + _true_category_secondary labels (propagate PR → PO → invoice for ML)."
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/sap_ariba/EBAN_PR_LINE_*.csv",
  format => "csv",
  header => true,
  inferColumnTypes => true
);
