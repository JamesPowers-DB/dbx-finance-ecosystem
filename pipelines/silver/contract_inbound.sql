-- ============================================================================
-- SILVER — contract_inbound (supplier-side contracts from Ariba)
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_silver}.contract_inbound
COMMENT "Inbound (procurement) contracts. Used for contract-leakage detection in Phase 2."
AS
SELECT
  'sap_ariba'                                   AS source_system,
  'ARIBA_CONTRACT_WORKSPACE'                    AS source_table,
  ContractWorkspaceId                           AS source_primary_key,
  ContractWorkspaceId                           AS contract_workspace_id,
  ContractType                                  AS contract_type,
  Title                                         AS title,
  AwardedSupplierId                             AS supplier_id,
  CAST(EffectiveDate AS DATE)                   AS effective_date,
  CAST(ExpirationDate AS DATE)                  AS expiration_date,
  CAST(TotalCommittedSpend AS DECIMAL(18,2))    AS total_committed_spend,
  CAST(ActualSpendToDate AS DECIMAL(18,2))      AS actual_spend_to_date,
  Status                                        AS status,
  OwningRegion                                  AS region
FROM ${schema_bronze_ariba}.ARIBA_CONTRACT_WORKSPACE;
