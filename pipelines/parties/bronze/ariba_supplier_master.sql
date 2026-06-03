-- ============================================================================
-- BRONZE — SAP Ariba supplier master (LFA1)
-- ============================================================================
-- Target schema: ${schema}
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema}.bronze_lfa1_supplier_master
COMMENT "SAP supplier master (LFA1). Source: Ariba export. ML hint: _supplier_category_primary and _maverick_propensity carry the supervised-label / drift signals used by spend classification."
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  _metadata.file_modification_time AS _ingested_at
FROM read_files(
  "/Volumes/${catalog}/${schema}/${raw_volume}/sap_ariba/LFA1_SUPPLIER_MASTER.csv",
  format => "csv",
  header => true,
  inferColumnTypes => true
);
