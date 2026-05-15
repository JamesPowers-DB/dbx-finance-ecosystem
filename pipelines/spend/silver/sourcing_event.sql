-- ============================================================================
-- SILVER — sourcing_event (Ariba RFQ / RFP / Auction)
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_silver}.sourcing_event
COMMENT "Conformed sourcing events. Awarded vs market amount feeds the Phase 2 savings-tracking metric."
AS
SELECT
  'sap_ariba'                                    AS source_system,
  'ARIBA_SOURCING_EVENT'                         AS source_table,
  EventId                                        AS source_primary_key,
  EventId                                        AS event_id,
  EventType                                      AS event_type,
  Title                                          AS title,
  OwnerOrgUnit                                   AS owner_org_unit,
  CAST(CreatedOn AS DATE)                        AS created_on,
  CAST(ClosedOn AS DATE)                         AS closed_on,
  SupplierInvitedCount                           AS suppliers_invited,
  SupplierRespondedCount                         AS suppliers_responded,
  AwardedSupplierId                              AS awarded_supplier_id,
  CAST(AwardedAmount AS DECIMAL(18,2))           AS awarded_amount,
  Status                                         AS status,
  YEAR(ClosedOn)                                 AS fiscal_year,
  QUARTER(ClosedOn)                              AS fiscal_quarter
FROM ${schema_bronze_ariba}.ARIBA_SOURCING_EVENT;
