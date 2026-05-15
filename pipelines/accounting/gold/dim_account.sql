-- ============================================================================
-- GOLD — dim_account (natural account)
-- ============================================================================

CREATE OR REFRESH MATERIALIZED VIEW ${schema_gold}.dim_account
COMMENT "Natural account dim. account_type maps COGS / SGA / RD / REVENUE / INTEREST / TAX / BS for FP&A roll-ups."
AS
SELECT DISTINCT
  natural_account_code                    AS account_code,
  natural_account_description             AS account_description,
  natural_account_type                    AS account_type
FROM ${schema_silver}.coa_account;
