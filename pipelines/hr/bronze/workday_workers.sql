-- ============================================================================
-- BRONZE — Workday workers (HR SCD Type 2 history)
-- ============================================================================
-- Target schema: ${schema_bronze_workday}
-- Reads from: /Volumes/${catalog}/${schema_raw}/${raw_volume}/workday/workers.csv
--
-- Workday-shaped column names: worker_id, worker_name_*, organization_id,
-- compensation_grade, effective_date / effective_through. Silver/gold rename
-- to Helios-canonical (employee_id, segment_code, seniority_band, …).
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_bronze_workday}.workers
COMMENT "Workday worker SCD2 history. One row per (worker × state change). Drives gold.dim_employees and downstream fact_emp_quarterly_cost."
AS SELECT
  *,
  _metadata.file_path                  AS _source_file,
  _metadata.file_modification_time     AS _ingested_at
FROM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/workday/workers.csv",
  format => "csv",
  header => true,
  inferColumnTypes => true
);
