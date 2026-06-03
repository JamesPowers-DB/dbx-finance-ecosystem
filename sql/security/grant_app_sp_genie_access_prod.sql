-- Grant the Spend Analytics app service principal access for Genie + analytics (PROD).
--
-- Catalog/schema are Databricks Asset Bundle variables (`var.catalog`, `var.schema`).
-- When run through the bundle they resolve to the deployed target (prod →
-- catalog `main`, schema `finance_spend_analytics`). For a manual run, substitute
-- the `${var.*}` tokens yourself, or run `python scripts/grant_app_sp_access.py
-- --target prod`, which fills the bundle variables AND resolves the SP automatically.
--
-- Replace `<APP_SP_PRINCIPAL>` with the app SP identifier (GRANT does not support
-- SQL variables — the grantee must be a backtick literal).
-- Find it: databricks apps get spend-analytics-prod -o json | jq .service_principal_client_id
--
-- Single schema; schema-level SELECT covers every current AND future table and
-- metric view (bronze_/silver_/gold_/ml_/meta_ prefixed) — never needs editing
-- when new objects are added.

GRANT USE CATALOG ON CATALOG ${var.catalog} TO `<APP_SP_PRINCIPAL>`;

GRANT USE SCHEMA, SELECT ON SCHEMA ${var.catalog}.${var.schema} TO `<APP_SP_PRINCIPAL>`;

-- Genie space CAN_RUN is a workspace ACL, not a UC grant — set it via the
-- permissions API (or let scripts/grant_app_sp_access.py do it):
--   databricks api patch /api/2.0/permissions/genie/<GENIE_SPACE_ID> --json \
--     '{"access_control_list":[{"service_principal_name":"<APP_SP_PRINCIPAL>","permission_level":"CAN_RUN"}]}'
