-- ============================================================================
-- BRONZE — In-house Contract Management System (commercial / outbound contracts)
-- ============================================================================
-- Target schema: ${schema_bronze_cms}
-- Reads files from: /Volumes/${catalog}/${schema_raw}/${raw_volume}/inhouse_cms/
-- Naming convention: clean flat snake_case, line-delimited JSON
--
-- Pattern: MATERIALIZED VIEW for flat one-shot files; STREAMING TABLE for
-- per-quarter wildcard globs (billing_schedule).
-- ============================================================================

-- ---- Flat files (batch read) -----------------------------------------------

CREATE OR REFRESH MATERIALIZED VIEW ${schema_bronze_cms}.contract
COMMENT "Outbound (revenue-side) commercial contract header. helios_entity_segment maps to HAD/HPA/HSB/HET."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/inhouse_cms/contract.jsonl",
  format => "json");

CREATE OR REFRESH MATERIALIZED VIEW ${schema_bronze_cms}.contract_party
COMMENT "Counterparties per contract (Helios + Customer rows)."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/inhouse_cms/contract_party.jsonl",
  format => "json");

CREATE OR REFRESH MATERIALIZED VIEW ${schema_bronze_cms}.contract_line_item
COMMENT "Line items on outbound contracts. Sum aligns to anchor revenue per (fiscal_year, fiscal_quarter, segment) within ±2%."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/inhouse_cms/contract_line_item.jsonl",
  format => "json");

CREATE OR REFRESH MATERIALIZED VIEW ${schema_bronze_cms}.contract_amendment
COMMENT "Amendment history per contract (extensions, value changes, scope/termination)."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/inhouse_cms/contract_amendment.jsonl",
  format => "json");

CREATE OR REFRESH MATERIALIZED VIEW ${schema_bronze_cms}.performance_obligation
COMMENT "ASC 606-style performance obligations per contract. Recognition pattern drives revenue waterfall."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/inhouse_cms/performance_obligation.jsonl",
  format => "json");

-- ---- Per-quarter files (streaming Auto Loader) -----------------------------

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_cms}.billing_schedule
COMMENT "Per-quarter billing events. Aggregate by (fiscal_year, fiscal_quarter, segment_code) ties to anchor revenue."
AS SELECT *, _metadata.file_path AS _source_file, _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/inhouse_cms/billing_schedule_*.jsonl",
  format => "json");
