-- Grant the Spend Analytics app service principal access for Genie + analytics (DEV).
--
-- Catalog/schema are Databricks Asset Bundle variables (`var.catalog`,
-- `var.schema_gold/silver/ml`). When this file is run through the bundle they
-- resolve to the deployed target's values (dev target → catalog
-- `horizontal_finance_dev`; the default is the prod catalog `horizontal_finance`).
-- For a manual run, either substitute the `${var.*}` tokens yourself or — easier —
-- run `python scripts/grant_app_sp_access.py --target dev`, which fills the bundle
-- variables AND resolves the service principal automatically.
--
-- Replace `<APP_SP_PRINCIPAL>` with the app SP identifier (GRANT does not support
-- SQL variables — the grantee must be a backtick literal; do NOT `SET ... = ...`).
-- Find it: databricks apps get spend-analytics-dev -o json | jq .service_principal_client_id
--   `6ceaa4bb-a2ee-4276-8c34-290a987c68a2`   (application / client id — preferred, stable)
--   `app-40zbx9 spend-analytics-dev`         (workspace SP display name — also valid)
--
-- Schema-level SELECT covers every current AND future table and metric view in the
-- schema, so this file never needs editing when new objects (e.g. mv_*) are added.

GRANT USE CATALOG ON CATALOG ${var.catalog} TO `<APP_SP_PRINCIPAL>`;

GRANT USE SCHEMA, SELECT ON SCHEMA ${var.catalog}.${var.schema_gold}   TO `<APP_SP_PRINCIPAL>`;
GRANT USE SCHEMA, SELECT ON SCHEMA ${var.catalog}.${var.schema_silver} TO `<APP_SP_PRINCIPAL>`;
GRANT USE SCHEMA, SELECT ON SCHEMA ${var.catalog}.${var.schema_ml}     TO `<APP_SP_PRINCIPAL>`;

-- Optional demo PR-writeback permissions (only if this SP writes PR rows directly):
-- GRANT USE SCHEMA ON SCHEMA ${var.catalog}.${var.schema_bronze_ariba} TO `<APP_SP_PRINCIPAL>`;
-- GRANT MODIFY ON TABLE ${var.catalog}.${var.schema_bronze_ariba}.EBAN_PR_LINE TO `<APP_SP_PRINCIPAL>`;

-- Genie space CAN_RUN is a workspace ACL, not a UC grant — set it via the
-- permissions API (or let scripts/grant_app_sp_access.py do it):
--   databricks api patch /api/2.0/permissions/genie/<GENIE_SPACE_ID> --json \
--     '{"access_control_list":[{"service_principal_name":"<APP_SP_PRINCIPAL>","permission_level":"CAN_RUN"}]}'
