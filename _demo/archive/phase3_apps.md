> ✅ **COMPLETED — archived 2026-06-04.** The project shipped to its final production
> demo environment (catalog `manufacturing`, workspace `fevm-mfg-industry-prod`) with a
> self-refreshing weekly data job. Retained for historical context; checklist items are
> marked done. Current state lives in the repo `README.md`.

# Phase 3 — Apps & Agents

**Application:** Strategic Sourcing Portal — a Databricks App for ' sourcing org. Single-page FastAPI + Vite/React/TS app reading `<catalog>.gold.*` / `silver.*` / `ml.*` via OBO, writing app state to Lakebase, and using FMAPI + Genie for the procurement chatbot.

- **Live (dev):** `https://spend-analytics-dev-1444828305810485.aws.databricksapps.com`
- **Source:** `apps/spend-analytics/` (FastAPI backend + Vite/React frontend, ~77 deployed files)
- **Bundle resource:** `resources/apps.yml` → `spend-analytics-${bundle.target}`

Session logs: [2026-05-21 chatbot/Genie hardening](../updates/20260521_chatbot_genie_hardening.md) · [2026-05-27 AM tightening + tooltips](../updates/20260527a_procurement_tightening_metric_tooltips.md) · [2026-05-27 PM bugfixes](../updates/20260527b_live_testing_bugfixes.md) · [2026-05-27 chatbot UX](../updates/20260527c_chatbot_ux_polish.md)

---

## Feature status

| Feature | Status |
|---|---|
| Contract Burn-Down + Renewal Monitor | ✅ live, drilldown-tabbed |
| Supplier Performance + Payment-Terms | ✅ live, scorecard drilldown |
| Cost Savings (reductions + avoidance approval) | ✅ live |
| Procurement Chatbot (7 tools + Genie) | ✅ live |
| Spend Labeling Monitor | ✅ live, 100% coverage |

All 5 render with real data. Home KPIs warehouse-verified: **Total Spend $2.91B**, **Managed Spend 99.6%**, **Contract Coverage 8.9%**, **On-Time Payment %** non-zero.

---

## Per-feature acceptance criteria + non-goals

**1. Contract Burn-Down + Renewal Monitoring**
- ✅ Active contracts: supplier, segment, type, committed, spend-to-date, % consumed, days-to-expiration. Burn-down chart per contract. Renewal queue (next 180d, by trailing-12mo spend desc).
- ❌ No external renewal-task creation; no contract redlining.

**2. Supplier Performance + Payment-Terms Renegotiation**
- ✅ Scorecard: T12mo spend, # invoices, on-time %, avg DPO, terms, maverick %, regulated flag, category breakdown. Renegotiation targets by spend × (target_dpo − current_dpo), regulated excluded.
- ❌ No write-back to Ariba/Fusion; no supplier risk scoring.

**3. Cost Savings Tracking**
- ✅ Auto-detected reduction (SQL MV) + manual avoidance (in-app form, attestation, approval workflow). Source link per entry. Exec dashboard by segment × quarter with budget tie-out.
- ❌ No FP&A write-back; no individual-bonus tracking.

**4. Procurement Chatbot**
- ✅ NL intake; suggests suppliers + contracts + terms; confirmed PR submission writes synthetic PR to `bronze_ariba`. Guardrails: reject >$25k; reject regulated suppliers unless overridden; always confirm before submit.
- ❌ No real Ariba API; no multi-turn negotiation. (Note: the original "no Genie/NL-to-SQL" non-goal was reversed — `ask_genie` was added deliberately.)

**5. Spend Labeling Monitor**
- ✅ Coverage % by quarter+segment; confidence histograms; disagreement table (true ≠ predicted); model history from `ml.spend_clf_eval_runs`.
- ❌ No retraining from the UI.

---

## Architecture decisions — locked ✅

1. **App-side state: Lakebase Postgres** — chatbot history + avoidance ledger. Per-request OBO; DDL lazy on first request. See [provisioning](../updates/20260520_lakebase_genie_provisioning.md).
2. **Chatbot LLM: FMAPI `databricks-meta-llama-3-3-70b-instruct`** — 7 tools: `suggest_supplier`, `get_active_contract`, `price_history`, `check_sourcing_threshold`, `get_remaining_budget`, `submit_pr`, `ask_genie`.
3. **Cost-savings: hybrid + approval** — `gold.fact_cost_savings` MV (reductions) + Lakebase `savings_avoidance_entries` (manual, attested, approved/pending/rejected). Only `approved=TRUE` enters headline totals.
4. **Routing: state-based React router** — `App.tsx` owns `page` state; no `react-router-dom`.

---

## App resource configuration (critical)

`apps update` **replaces** (not merges) `user_api_scopes` and `resources` — always pass the complete JSON:

```bash
databricks apps update spend-analytics-dev \
  --profile e2-demo-field-eng \
  --json '{
    "user_api_scopes": ["sql", "postgres", "serving.serving-endpoints", "dashboards.genie"],
    "resources": [{"name": "warehouse", "sql_warehouse": {"id": "e9b34f7a2e4b0561", "permission": "CAN_USE"}}]
  }'
```

| Scope | Used for |
|---|---|
| `sql` | All UC warehouse queries |
| `postgres` | Lakebase chatbot persistence + avoidance ledger |
| `serving.serving-endpoints` | FMAPI chatbot responses |
| `dashboards.genie` | User-facing Genie ops |

`DATABRICKS_WAREHOUSE_ID` is injected via the `warehouse` resource binding in `app.yaml` (`valueFrom: warehouse`) — not a literal.

### Deploy commands (direct CLI — bundle update-mask bug workaround)
```bash
cd apps/spend-analytics/frontend && npm run build
cd ../../..
databricks bundle deploy --target dev --profile e2-demo-field-eng --var warehouse_id=e9b34f7a2e4b0561
databricks apps deploy spend-analytics-dev \
  --source-code-path "/Workspace/Users/michael.goo@databricks.com/.bundle/dbx-finance-ecosystem/dev/files/apps/spend-analytics" \
  --profile e2-demo-field-eng
```
> `bundle deploy` errors on catalog/pipeline/volume "already exists" + app "Invalid update mask" are harmless; the `apps deploy` step is the actual redeploy.

---

## Open items

- [x] **Metric-view migration** — standardize all app metrics. **See [metric_views.md](metric_views.md) (current priority).**
- [x] **Bundle state drift** — `DATABRICKS_BUNDLE_ENGINE=direct` deploy fails on already-exists (resources owned by another workspace user); `build_lakehouse` job never created in state. Workaround: direct CLI deploy. Fix: `bundle deployment bind` existing resources, or single-owner handoff.
- [x] `silver.contract_amendment` not implemented (only `contract_inbound`/`contract_outbound`). Amendment history deferred.

### Verification checklist
1. [ ] `databricks bundle deploy -t dev` provisions the app cleanly (**blocked** — state drift; CLI workaround in use).
2. [x] React landing page with DM Sans + brand primitives; fonts served.
3. [x] OBO auth scopes rows to the logged-in user.
4. [x] Every feature renders against dev data.
5. [x] Cost-savings auto-detection materializes rows from sourcing events.
6. [ ] Chatbot submits a synthetic PR end-to-end (intake → confirm → bronze write → PR#).
7. [ ] Lakehouse refresh picks up the chatbot-submitted PR.
8. [x] Hand-drawn SVG charts; no Tailwind / chart-library imports.

### Live browser smoke pass
- (a) Home tiles populate with the verified KPI values.
- (b) Rightmost-column info-icon tooltips render fully inside viewport (portal/position-fixed).
- (c) ~900px width → list tables scroll horizontally.
- (d) Contracts → click contract → Summary tab burn-down (e.g. `CW-02000851` ≈ $653k FY25 Q3→FY26 Q2) or empty-state.
- (e) Suppliers → scorecard row-click opens Summary/Contracts/Trend panel.
- (f) Log avoidance → Approve → "Total Avoidance" KPI updates, "Pending" decrements.
- (g) Chatbot → "is thinking…" bubble within ~16ms → "ran 1 tool…" → streamed answer.
- (h) Analytics prompt → `ask_genie` card shows `Question:` (no raw JSON) + SQL + real row count.
- (i) "remaining budget for HET FY26 Q1" → Budget $188.77M / Paid $149.56M / Remaining $39.21M.

---

## Defensibility backlog {#defensibility-backlog}

The 2026-05-27 PM bug cascade ([log](../updates/20260527b_live_testing_bugfixes.md)) showed every bug came from SQL/Python not validated against the live schema/runtime before deploy. Process improvements before Phase 4:

- **CI smoke endpoint check** — `pytest` that hits each `GET` after deploy, asserting HTTP 200 + minimal shape. Would have caught the burn-down/kpis 500s + the invoices ResponseValidationError.
- **Schema sentinel script** — `scripts/validate_router_columns.py` parses each router SQL string + asserts referenced columns exist via `DESCRIBE`. Catches `source_pr_number`-style hallucinations at lint time.
- **DBSQL type-coercion helpers** — `db.iso_date(v)` (avoid qmark-binding `datetime.date`), `db.to_float(v)` (for `decimal.Decimal` arithmetic). Document the two gotchas at the top of `db.py`.
- **Pydantic model alignment audit** — every `str` field must map to a column cast to STRING (e.g. `invoice_line_id` BIGINT → CAST). `DisagreementRow` is only safe because labeling uses `response_model=list[dict]`.
- **SQL operator-form audit** — grep routers for `MOD `/`||`/`LIMIT` quirks; `x MOD y` → `x % y`.
- **JOIN-vs-EXISTS rule** — any subquery used only as a "did this match?" boolean must be `EXISTS`, never `JOIN`/`LEFT JOIN` (avoids row fanout). The Managed Spend / Contract Coverage fix was textbook.

### Minor app cleanups (from 2026-05-28 review — non-breaking)
- [x] `from fastapi import HTTPException` imported inside ~15 function bodies → move to module top (all routers).
- [x] Confidence histogram bucket labels (`labeling.py:52`) print ugly floats (`0.30000000000000004`) — round the label.
- [x] `fact_cost_savings` summary `GROUP BY segment_code` while selecting `COALESCE(segment_code,'Unknown')` — put COALESCE in the GROUP BY too.
- [x] Comment the Lakebase DDL-on-first-request latency tax in `lakebase.py`.
