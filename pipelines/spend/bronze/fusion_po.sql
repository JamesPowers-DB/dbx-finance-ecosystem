-- ============================================================================
-- BRONZE — Oracle Fusion Purchase Orders
-- ============================================================================
-- Target schema: ${schema_bronze_fusion}
-- Reads files from: /Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/
--
-- POs originate as released Ariba PRs (EBAN.STATU='B') and are issued in
-- Fusion. po_headers_all.source_requisition_number_ext links back to
-- EBAN.BANFN — that's the cross-system bridge.
-- ============================================================================

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_fusion}.po_headers_all
COMMENT "Oracle Fusion PO headers (per-quarter). source_requisition_number_ext FKs to Ariba EBAN.BANFN. type_lookup_code in (STANDARD, FRAMEWORK)."
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/po_headers_all_*.csv",
  format => "csv",
  header => true,
  inferColumnTypes => true
);

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_fusion}.po_lines_all
COMMENT "Oracle Fusion PO lines (per-quarter parquet). Inherits item_description, quantity, unit_price from upstream PR with light negotiation (0.95-1.02× PR estimate). Carries _segment_code and the 2-tier _true_category_primary + _true_category_secondary labels for downstream silver/gold + ML label propagation."
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/oracle_fusion/po_lines_all_*.parquet",
  format => "parquet"
);
