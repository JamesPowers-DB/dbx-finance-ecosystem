-- ============================================================================
-- BRONZE — In-house CMS contracts (outbound / commercial contracts)
-- ============================================================================
-- Target schema: ${schema_bronze_cms}
-- ============================================================================

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
