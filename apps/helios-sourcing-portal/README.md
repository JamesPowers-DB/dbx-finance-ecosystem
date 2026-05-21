# Helios Strategic Sourcing Portal

A Databricks App for Helios' sourcing organization. FastAPI backend + Vite/React/TS frontend, OBO auth, hand-drawn SVG charts on the Databricks brand design system.

## Features

1. **Contract Burn-Down + Renewal Monitoring** — active contracts with % consumed, days to expiration, renewal queue sorted by trailing spend.
2. **Supplier Performance + Payment-Terms Renegotiation** — scorecard with on-time %, avg DPO, maverick propensity; targeting view for working-capital gains.
3. **Cost Savings Tracking** — auto-detected reductions from sourcing events + manual avoidance entry form; executive dashboard vs FP&A budget.
4. **Procurement Chatbot** — FMAPI (Llama 3.3 70B) with 5 tools: suggest_supplier, get_active_contract, price_history, check_budget_threshold, submit_pr. PR submission writes to bronze_ariba.
5. **Spend Labeling Monitor** — ML coverage by quarter, confidence histograms, disagreement table, model eval history.

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
- **Auth**: OBO via `X-Forwarded-Access-Token` — every UC query runs as the logged-in user.
- **App state**: Lakebase Postgres (`chatbot_sessions`, `chatbot_messages`, `savings_avoidance_entries`)
