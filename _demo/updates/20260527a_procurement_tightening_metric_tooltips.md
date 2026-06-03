# 2026-05-27 (AM) — Procurement tightening + metric tooltips

Two back-to-back passes: backend metric defensibility / drilldown UX / savings approval workflow, then a structured-tooltip layer across every metric surface. All TypeScript clean, Vite production build green (266 modules, 272 kB / 81 kB gzip).

## Priority 1 — Suspicious metric logic + query patterns (backend SQL/Python)

- **Paid-only spend filter** — every `fact_invoices` aggregate in `system.py`, `suppliers.py`, `contracts.py`, `chatbot.py` now adds `payment_status = 'PAID'`. Unpaid + past-due invoices no longer count as realized spend.
- **Redefined `managed_spend_pct`** — was % of addressable with ML-predicted category (misleading "Managed Spend" label); now = addressable paid spend `po_matched_flag='Y'` OR matched to an active contract for the same supplier inside the contract's effective window, divided by addressable paid spend. The old ML-coverage metric is surfaced separately as `classified_spend_pct` (Labeling page).
- **Fixed `contract_coverage_pct`** — was multi-year contract commitments / T12M invoice spend (could exceed 100%). Now = T12M paid invoices matched to an active contract / T12M addressable paid spend, same window on both sides.
- **Active contracts must be date-valid** — added `effective_date <= CURRENT_DATE() AND expiration_date >= CURRENT_DATE()` to "Active" predicates in `contracts.py` list, `renewals`, and `suppliers.py` scorecard contracts subquery. Status alone was admitting expired rows.
- **Spend-weighted On-Time Payment %** — formula changed from `SUM(is_on_time)/COUNT(*)` to `SUM(amount WHERE is_on_time)/SUM(amount)` in `system.py` and `suppliers.py`. Renamed to "On-Time Payment %" everywhere.
- **T12M window aligned across scorecard columns** — `invoice_count`, `on_time_payment_pct`, `avg_dpo` were all-time while `trailing_12m_spend` was 365-day. All four now share the same predicate via `_supplier_t12m_agg_sql()` CTE in `suppliers.py`.
- **Measured maverick %** — replaced synthetic `dim_supplier.maverick_propensity` (random demo seed) with `measured_maverick_pct` = % of T12M paid spend NOT matched to an active contract for that supplier.
- **`get_remaining_budget` chatbot tool** — `check_budget_threshold` was a static $25k rule pretending to be a budget check. Renamed to `check_sourcing_threshold`; added `get_remaining_budget(segment_code, fiscal_year, fiscal_quarter)` querying `fact_fpa_budgets` (COGS+SGA) minus `fact_invoices` paid spend. `suggest_supplier` ranks by measured maverick; `price_history` uses quantity-weighted unit price.
- **Centralized T12M helper** — `db.t12m_supplier_spend_sql()` returns the canonical T12M paid-spend subquery; six duplicated copies across four routers now reference one source. `PAID_PREDICATE` constant.

## Priority 2 — Contract drilldown

- **Burn-down is now contract-scoped** — was summing ALL invoices for the contract's supplier. Now joins `fact_invoices` by `supplier_id` AND `invoice_date BETWEEN c.effective_date AND c.expiration_date` AND `payment_status='PAID'`. List-view `pct_consumed` recomputed the same way via `_contract_scoped_consumption_sql()`.
- **New endpoints**: `GET /api/contracts/{id}/invoices` and `/purchase_orders`, both reusing the contract-scope filter.
- **Drilldown panel now tabbed** — 400px right-side panel gains **Summary | Invoices | POs**, lazy-loaded, + metadata grid + close button.

## Priority 3 — Supplier scorecard drilldown

- **Wired `/api/suppliers/{id}/scorecard`** (was defined and unused). Row click opens inline 400px panel: header + 6-cell `PanelStat` strip (T12M Spend, Invoices, On-Time %, Avg DPO, Maverick %, Terms) + tabs **Summary | Contracts | Trend**.
- **Tightened the scorecard query** — paid-only + T12M; contracts subquery filters to active + currently effective; `spend_trend` returns last 8 quarters for the `SparklineChart`.

## Priority 4 — Normalized cost avoidance logging

- **Lakebase DDL extended idempotently** — `savings_avoidance_entries` gains `approved_by`, `approved_at`, `rejected_at`, `rejection_reason` via `ALTER TABLE … ADD COLUMN IF NOT EXISTS`.
- **Approval endpoints** — `POST /api/cost_savings/avoidance/{id}/approve` and `/reject` (reject takes `{reason}`). Sets `approved_by` = caller email.
- **Summary fixed** — filters avoidance to `approved = TRUE` for headline totals; surfaces `pending_avoidance_usd` separately. Full-outer join over `(segment, fiscal_year, fiscal_quarter)` so avoidance-only quarters appear.
- **Form gains Segment + Supplier autocomplete**; avoidance table gains Approve/Reject buttons.
- **Honesty fix**: replaced every `SELECT *` with explicit `_AVOIDANCE_COLS`.

## Metric tooltips (live)

- **New `MetricTooltip` component** — popover with **Period / Definition / Formula / Filters**. Wraps an existing element so it adds no extra glyphs to clickable surfaces.
- **Single catalog** (`metricDefinitions.ts`) — `METRICS` object with 35+ stable keys. Single artifact to edit before a demo to refine wording; page components never inline metric copy.
- **`HeaderLabel` helper** + **`StatTile` extended** with optional `tooltip?` prop.
- **Wired surfaces**: Home (4 KPIs); CostSavings; Contracts; Suppliers; LabelingMonitor.
- **Out of scope**: no CSV/Excel export, no new screens, no URL routing, no external tooltip library.
