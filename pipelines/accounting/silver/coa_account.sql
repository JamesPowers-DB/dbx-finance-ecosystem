-- ============================================================================
-- SILVER — coa_account (chart of accounts)
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_silver}.coa_account
COMMENT "7-segment Oracle COA. natural_account_type categorizes accounts as COGS / SGA / RD / REVENUE / INTEREST / TAX / BS for fact_gl_entries roll-ups."
AS
SELECT
  'oracle_fusion'                       AS source_system,
  'gl_code_combinations'                AS source_table,
  CAST(code_combination_id AS STRING)   AS source_primary_key,
  CAST(code_combination_id AS BIGINT)   AS code_combination_id,
  segment1_entity                       AS entity_code,
  segment2_cost_center                  AS cost_center_code,
  segment3_natural_account              AS natural_account_code,
  segment4_product                      AS product_code,
  segment5_intercompany                 AS intercompany_code,
  segment6_future1,
  segment7_future2,
  natural_account_description,
  natural_account_type,
  CASE _helios_segment_code
    WHEN 'HAD' THEN 'HAD' WHEN 'HPA' THEN 'HPA'
    WHEN 'HSB' THEN 'HSB' WHEN 'HET' THEN 'HET'
    WHEN 'CORP' THEN 'CORP' ELSE 'OTHER'
  END                                   AS segment_code,
  enabled_flag
FROM ${schema_bronze_fusion}.gl_code_combinations;
