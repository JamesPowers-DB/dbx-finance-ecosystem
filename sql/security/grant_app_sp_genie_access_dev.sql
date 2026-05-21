-- Grant the Helios app service principal access for Genie + analytics (DEV).
-- Replace `<APP_SP_PRINCIPAL>` with the app SP principal identifier.
-- Example principal values:
--   `7810c2cb-5c97-4458-80bb-078604c9b89b`  (application/client id)
--   `app-40zbx9 helios-sourcing-portal-dev` (workspace SP display name)

GRANT USE CATALOG ON CATALOG horizontal_finance_dev TO `<APP_SP_PRINCIPAL>`;

GRANT USE SCHEMA ON SCHEMA horizontal_finance_dev.gold TO `<APP_SP_PRINCIPAL>`;
GRANT USE SCHEMA ON SCHEMA horizontal_finance_dev.silver TO `<APP_SP_PRINCIPAL>`;
GRANT USE SCHEMA ON SCHEMA horizontal_finance_dev.ml TO `<APP_SP_PRINCIPAL>`;

GRANT SELECT ON TABLE horizontal_finance_dev.gold.fact_invoices TO `<APP_SP_PRINCIPAL>`;
GRANT SELECT ON TABLE horizontal_finance_dev.gold.dim_supplier TO `<APP_SP_PRINCIPAL>`;
GRANT SELECT ON TABLE horizontal_finance_dev.gold.fact_purchase_requests TO `<APP_SP_PRINCIPAL>`;
GRANT SELECT ON TABLE horizontal_finance_dev.gold.fact_purchase_orders TO `<APP_SP_PRINCIPAL>`;
GRANT SELECT ON TABLE horizontal_finance_dev.gold.fact_cost_savings TO `<APP_SP_PRINCIPAL>`;
GRANT SELECT ON TABLE horizontal_finance_dev.gold.dim_spend_category TO `<APP_SP_PRINCIPAL>`;
GRANT SELECT ON TABLE horizontal_finance_dev.silver.contract_inbound TO `<APP_SP_PRINCIPAL>`;
GRANT SELECT ON TABLE horizontal_finance_dev.silver.sourcing_event TO `<APP_SP_PRINCIPAL>`;
GRANT SELECT ON TABLE horizontal_finance_dev.ml.invoice_classifications TO `<APP_SP_PRINCIPAL>`;

-- Optional demo PR writeback permissions (only needed if this SP writes PR rows directly):
-- GRANT USE SCHEMA ON SCHEMA horizontal_finance_dev.bronze_ariba TO `<APP_SP_PRINCIPAL>`;
-- GRANT MODIFY ON TABLE horizontal_finance_dev.bronze_ariba.EBAN_PR_LINE TO `<APP_SP_PRINCIPAL>`;
