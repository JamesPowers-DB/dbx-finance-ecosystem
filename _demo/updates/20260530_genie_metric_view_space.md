# 2026-05-30 — Genie space rebuilt on metric views (+ 3 new metric views)

Tore down the old Genie space and recreated it as a **metric-view-only** space, so
its answers can't drift from the app/dashboard KPIs. Added the metric views needed
to cover the full spend lifecycle (contracts, purchase orders, savings).

## New / changed metric views (`metric_views/apply_metric_views.py`)

| View | Source | Purpose |
|---|---|---|
| `gold.mv_contracts` | `silver.contract_inbound` (+ `dim_supplier` join) | Buy-side contract portfolio. `utilization_rate` = actual/committed (~40.7%) answers "% of contracts utilized". Committed vs actual, expiring-in-90d, over-utilized. |
| `gold.mv_purchase_orders` | `fact_purchase_orders` LEFT JOIN `fact_purchase_requests` | Request→order step. PO dollars, **off-contract PO leakage** by PR source channel, PRs converted, estimate vs committed. |
| `gold.mv_cost_savings` | `fact_cost_savings` | Sourcing-event savings by event type/segment/supplier (low priority). |
| `gold.mv_spend` | (unchanged source) | Added `active_periods` measure (consistency signal). |
| `gold.mv_supplier_performance` | nested on `mv_spend` | Added `governed_spend_pct`, `active_periods`, and **`reliability_score`**. |

**Reliability is a governance index, not delivery quality.** There is no
supplier delivery/quality/fill-rate data in the model (the only timing signals
describe *our* AP behaviour). So "most reliable suppliers" =
`0.5·(1−maverick) + 0.3·managed_coverage + 0.2·consistency(active_qtrs/8)`, ranked
with a minimum trailing-spend filter so one-off vendors don't top the list.

All five views validated in dev: total spend $2.96B, managed 50.6%, contract
coverage 48.5%, contract utilization 40.7%, off-contract PO 49.1%.

## Genie space

- **Old**: `01f154f176351736be32d20533d9f257` — **deleted** (queried raw tables).
- **New**: `01f15c3823f2163a9560dadb4357bb31` — **Strategic Spend Analytics**, curated to
  the five metric views only. Robust instructions (metric-view-only rule, managed-spend
  + reliability + utilization + best-payment-terms definitions, lifecycle, cross-view
  linkage), 6 curated example question→SQL pairs, 4 benchmarks, 6 sample questions.
- **Provisioning**: `genie/provision_genie_space.py` — parameterized by
  `--catalog/--schema-gold/--warehouse-id`, builds the v2 `serialized_space` and
  creates/updates/recreates via the Genie REST API (`databricks api`, honors `--profile`).
  Same dev/prod definition, no hardcoded catalog.
- **`GENIE_SPACE_ID`** updated in `apps/spend-analytics/app.yaml`.

### Validation (my user token, via `ask_genie`)
All four target questions answered correctly using `MEASURE()` over the metric views:
- "Who are my top 5 vendors?" → CVS Pharmacy, Monk Real Estate, El Paso, Intel, TLC.
- "What percent of contracts have been utilized?" → 40.74%.
- "Who are our most reliable suppliers?" → ranked by `reliability_score` (Future Bright, Stratabiz, TLC…).
- "Which PR channels leak the most off-contract spend?" → ManualSubmission 64.9%, ProcurementAgent 64.7%.

## ⚠️ Follow-ups (app SP access)

The in-app chatbot calls Genie with the **app service principal** token, which was
only validated above with a *user* token. Before the app chatbot works against the
new space:
1. Run `sql/security/grant_app_sp_genie_access_dev.sql` (now grants `SELECT` on the
   five metric views too).
2. Grant the app SP `CAN_RUN` on space `01f15c3823f2163a9560dadb4357bb31` (Genie UI /
   permissions API — not a SQL grant).
3. Re-run `scripts/validate_genie_sp_access.py` (its `PROBE_OBJECTS` now point at the
   metric views).
