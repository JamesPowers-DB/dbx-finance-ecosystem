-- ============================================================================
-- BRONZE — Ariba sourcing events + supplier performance scorecards
-- ============================================================================
-- POs and invoices moved to Fusion. What's left from Ariba on the spend side:
-- sourcing events (RFQ/RFP/Auction) and quarterly supplier scorecards.
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_bronze_ariba}.ARIBA_SOURCING_EVENT
COMMENT "Ariba sourcing events (RFQ / RFP / Auction). AwardedAmount feeds Phase 2 savings-tracking."
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  _metadata.file_modification_time AS _ingested_at
FROM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/sap_ariba/ARIBA_SOURCING_EVENT.csv",
  format => "csv",
  header => true,
  inferColumnTypes => true
);

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_ariba}.ARIBA_SUPPLIER_PERFORMANCE
COMMENT "Quarterly Ariba supplier scorecards. OnTimeDeliveryPct correlates with supply-chain-stress macro index."
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/sap_ariba/ARIBA_SUPPLIER_PERFORMANCE_*.csv",
  format => "csv",
  header => true,
  inferColumnTypes => true
);
