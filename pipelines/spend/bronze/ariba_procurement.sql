-- ============================================================================
-- BRONZE — SAP Ariba procurement (POs, invoices, sourcing, supplier scorecards)
-- ============================================================================
-- Target schema: ${schema_bronze_ariba}
-- Reads files from: /Volumes/${catalog}/${schema_raw}/${raw_volume}/sap_ariba/
-- ============================================================================

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_ariba}.EKKO_PO_HEADER
COMMENT "SAP PO header (EKKO). One row per purchase order. Per-quarter file partitioned by AEDAT."
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/sap_ariba/EKKO_PO_HEADER_*.csv",
  format => "csv",
  header => true,
  inferColumnTypes => true
);

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_ariba}.EKPO_PO_LINE
COMMENT "SAP PO line item (EKPO). ~5 lines per PO. TXZ01 is the free-text description used as input feature for spend classification; _true_spend_category is the ground-truth label."
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/sap_ariba/EKPO_PO_LINE_*.csv",
  format => "csv",
  header => true,
  inferColumnTypes => true
);

CREATE OR REFRESH STREAMING TABLE ${schema_bronze_ariba}.RBKP_INVOICE_HEADER
COMMENT "SAP supplier invoice header (RBKP). ~80% match an EKKO header (3-way match); remainder are non-PO direct vouchers."
AS SELECT
  *,
  _metadata.file_path AS _source_file,
  _metadata.file_modification_time AS _ingested_at
FROM STREAM read_files(
  "/Volumes/${catalog}/${schema_raw}/${raw_volume}/sap_ariba/RBKP_INVOICE_HEADER_*.csv",
  format => "csv",
  header => true,
  inferColumnTypes => true
);

CREATE OR REFRESH MATERIALIZED VIEW ${schema_bronze_ariba}.ARIBA_SOURCING_EVENT
COMMENT "Ariba sourcing events (RFQ / RFP / Auction). AwardedAmount feeds the Phase 2 savings-tracking metric."
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
