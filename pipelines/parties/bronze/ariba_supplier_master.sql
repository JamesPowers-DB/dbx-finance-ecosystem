-- ============================================================================
-- BRONZE — SAP Ariba supplier master (LFA1)
-- ============================================================================
-- Target schema: ${schema_bronze_ariba}
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_bronze_ariba}.LFA1_SUPPLIER_MASTER
COMMENT "SAP supplier master (LFA1). Source: Ariba export. ML hint: _supplier_category_primary and _maverick_propensity carry the supervised-label / drift signals used by spend classification."
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  _metadata.file_modification_time AS _ingested_at
FROM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/sap_ariba/LFA1_SUPPLIER_MASTER.csv",
  format => "csv",
  header => true,
  inferColumnTypes => true
);
