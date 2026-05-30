# 2026-05-20/21 — Lakebase + Genie Space provisioning

## Lakebase — provisioned ✅ (2026-05-20)

- **Project**: `projects/spend-analytics` on `e2-demo-field-eng`
- **Endpoint**: `ep-blue-cake-d1dw80zo.database.us-west-2.cloud.databricks.com:5432`
- **Database**: `databricks_postgres`
- **Auth pattern**: per-request OBO — each connection uses the calling user's Databricks token via `w.postgres.generate_database_credential()`. DDL (`chatbot_sessions`, `chatbot_messages`, `savings_avoidance_entries`) runs lazily on the first authenticated user request.
- **Why no SP pool**: the app's service principal is not granted a Postgres role in the Lakebase instance. OBO per-request avoids this entirely and aligns with the rest of the app's auth model.
- **Config**: `LAKEBASE_HOST`, `LAKEBASE_ENDPOINT`, `LAKEBASE_DATABASE` set in `apps/spend-analytics/app.yaml`.

## Genie Space — provisioned ✅ (2026-05-21)

- **Space**: `Strategic Spend Analytics` — `01f154f176351736be32d20533d9f257`
- **Tables**: `gold.fact_invoices`, `gold.dim_supplier`, `gold.fact_purchase_requests`, `gold.fact_purchase_orders`, `gold.fact_cost_savings`, `gold.dim_spend_category`, `silver.contract_inbound`, `silver.sourcing_event` (all in `horizontal_finance_dev`)
- **Warehouse**: `Serverless Starter Warehouse` (`e9b34f7a2e4b0561`)
- **Integration**: wired as the `ask_genie` tool in `chatbot.py`. `GENIE_SPACE_ID` in `app.yaml`; `genie_space_id` in `config.py`.
- **SP-only auth**: Genie Conversation REST API uses the app SP M2M token from `APP_SP_CLIENT_ID`/`APP_SP_CLIENT_SECRET` (removes user-token scope drift from chatbot analytics responses).
- **Curate**: add instructions + certified queries in the Databricks UI to improve SQL generation quality for procurement-specific metrics.

> ⚠️ **Follow-up (see [metric views](../todo/phase1_consumption.md))**: Genie writes its own SQL over the raw tables, so its numbers can diverge from the app's KPIs (e.g. "total spend" with no PAID filter). Repointing the Genie Space at the metric views will unify the two.

### SP permission verification

```bash
python scripts/validate_genie_sp_access.py \
  --profile e2-demo-field-eng \
  --host e2-demo-field-eng.cloud.databricks.com \
  --genie-space-id 01f154f176351736be32d20533d9f257 \
  --sp-client-id "$APP_SP_CLIENT_ID" \
  --sp-client-secret "$APP_SP_CLIENT_SECRET"
```

Grant files (run in SQL editor if UC probes fail): `sql/security/grant_app_sp_genie_access_dev.sql`, `sql/security/grant_app_sp_genie_access_prod.sql`.
