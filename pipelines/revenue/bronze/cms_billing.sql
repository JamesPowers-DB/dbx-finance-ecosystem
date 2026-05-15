-- ============================================================================
-- BRONZE — In-house CMS billing schedule (revenue trigger events)
-- ============================================================================
-- Target schema: ${schema_bronze_cms}
-- ============================================================================

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_cms}.billing_schedule
COMMENT "Per-quarter billing events. Aggregate by (fiscal_year, fiscal_quarter, segment_code) ties to anchor revenue."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/inhouse_cms/billing_schedule_*.jsonl",
  format => "json");
