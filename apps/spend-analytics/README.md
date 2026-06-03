# Strategic Spend Analytics

An auxiliary Databricks App surface for end-to-end spend visibility. FastAPI backend + Vite/React/TS frontend, OBO auth, hand-drawn SVG charts on the Databricks brand design system.

## Features

1. **Spend Analytics** — funnel-led overview: lifecycle funnel (PR→PO→paid), grain-toggle spend trend, composition drill, supplier Pareto, leverage table. All from the governed `mv_spend` / `mv_purchase_orders` metric views.
2. **Contracts** — inline-expand records ranked by renewal risk (expiring / under-utilized / exhausted), burn-down, terms, linked invoices + POs.
3. **Supplier Performance** — inline-expand scorecard: ML classification, spend-over-time, top PO commitments, dimensional attributes, and a client-side renegotiation what-if model.
4. **Savings Register** — one unified ledger of cost reductions (hard) + cost avoidances (soft), each tied to a sourcing event or contract, with a submit → attest workflow. Lakebase-backed; **seeded from real artifacts** (see [Cost Savings register — data & seeding](#cost-savings-register--data--seeding)).
5. **Procurement Chatbot** — FMAPI (`databricks-claude-sonnet-4-6`) tool-calling agent with: `find_suppliers`, `supplier_profile`, `get_active_contract`, `price_history`, `expiring_contracts`, `savings_summary`, `submit_pr`, and `ask_genie` (open-ended analytics fallback over the governed Genie space). `submit_pr` is a **simulated** procurement action — large/regulated buys route to Sourcing & Contracting, others mint a PR number — mirroring an MCP action with no DB write. Sessions/messages persist in Lakebase.

## Local dev

```bash
# Backend
cd backend
uv sync
export APP_DEV_ALLOW_ANONYMOUS=1
export DATABRICKS_HOST=https://e2-demo-field-eng.cloud.databricks.com
export DATABRICKS_WAREHOUSE_ID=<warehouse-id>
export DATABRICKS_CATALOG=horizontal_finance_dev
uv run uvicorn backend.main:app --reload --port 8000

# Frontend (separate terminal)
cd frontend
npm install
npm run dev   # :5173, proxies /api → :8000
```

## Deploy

```bash
# From repo root
./apps/build_frontends.sh
databricks bundle validate -t dev
databricks bundle deploy -t dev
```

## Architecture

- **Backend**: FastAPI, `databricks-sql-connector` (OBO per request), `psycopg3` (Lakebase app state), `databricks-sdk` (FMAPI chatbot)
- **Frontend**: Vite + React 18 + TypeScript. No Tailwind, no UI library, no chart library. Hand-drawn SVG with d3-scale math.
- **Auth (UC reads)**: OBO via `X-Forwarded-Access-Token` — every warehouse query runs as the logged-in user.
- **Auth (Lakebase)**: `lakebase._conninfo` mints a per-request OAuth credential. It **prefers the app service principal** (if the runtime exposes `DATABRICKS_CLIENT_ID/SECRET`) and **falls back to the OBO caller** otherwise — this app runtime does not expose SP M2M creds to the SDK, so it connects as the calling user, who must have a Lakebase Postgres role (`postgres_role` = their email). The SP, if used, connects as `postgres_role` = its client id. Requires the `postgres` user_api_scope.
- **App state**: Lakebase Postgres on project `finance-horizontals`, database `bizapps-spend` — tables `savings_register`, `chatbot_sessions`, `chatbot_messages` (DDL is lazy; see below).

## Cost Savings register — data & seeding

The Savings Register is the app's flagship **Lakebase** (operational write) surface. All of it lives in [`backend/routers/cost_savings.py`](backend/routers/cost_savings.py) + the Lakebase DDL in [`backend/lakebase.py`](backend/lakebase.py). There is **no separate seed job** — schema creation and seeding are **lazy**, on first use:

1. **DDL** — the first Lakebase request runs `_ensure_ddl()` (`lakebase.py`), creating `savings_register` (+ chatbot tables) `IF NOT EXISTS`.
2. **Seed** — `_ensure_seeded(caller)` (`cost_savings.py`) runs at the top of `GET /cost_savings/register` and `GET /cost_savings/kpis`. It:
   - `SELECT COUNT(*) FROM savings_register` — if non-empty, it flips an in-process flag and returns (so it runs **once** and never re-seeds once rows exist; your real submissions are safe).
   - otherwise reads **real artifacts** from Unity Catalog via the warehouse: top **24** reductions from `gold.fact_cost_savings` (sourcing events) + top **18** active contracts from `silver.contract_inbound`.
   - `_build_seed_rows()` turns those into ~**42** ledger rows — assigning hard/soft savings types (the 10-item `SAVINGS_TYPES` taxonomy), fabricated submitter/attester names, and a mix of `pending` / `attested` / `rejected` statuses (so there are pending items to attest live).
   - bulk-inserts via `executemany` with `ON CONFLICT (record_id) DO NOTHING` (idempotent even under a race).

So the seeded records are **fabricated context tied to real sourcing events and contracts** — every row deep-links to an artifact that exists in the data.

**Re-seed / reset:** the seed only runs when the table is empty, so it won't clobber real data. To force a fresh seed (e.g. after changing the seed logic), `TRUNCATE savings_register;` in the Lakebase SQL editor and reload the page. To wipe a single demo, `DELETE` the rows you don't want.

**Note:** `savings_avoidance_entries` (an earlier split-model table) is still created by the DDL but is unused by the current unified register — safe to ignore or drop.
