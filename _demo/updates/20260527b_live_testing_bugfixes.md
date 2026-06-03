# 2026-05-27 (PM) — Bug fixes from live testing

Five issues surfaced during the post-deploy smoke test, fixed through four sequential redeploys. Final deployment `01f159dbb80716f68573ce2a410bdfa0` (14:53:16Z).

> **Process lesson (see [defensibility backlog](../todo/phase3_apps.md#defensibility-backlog)):** every bug came from SQL/Python not validated against the live schema or runtime before deploy.

## Issue 1 — Tooltip clipping on rightmost columns
CSS-only `:hover` tooltip was clipped by the table's `overflow-x: auto`, the page scroll container, and the 400px drilldown panels. Fix: rewrote `MetricTooltip.tsx` to React state + `useRef` + `createPortal(document.body)` with `position: fixed` from `getBoundingClientRect()`. Auto-flips near viewport edges. Public API unchanged.

## Issue 2 — Column values not triggering horizontal scroll
Tables used `width: 100%`, compressing columns instead of growing. Fix: `min-width: 100%` on all main list tables (Contracts, Suppliers, CostSavings, LabelingMonitor); wrapped CostSavings Avoidance + all 3 LabelingMonitor tables in `overflowX: auto`. Drilldown-panel sub-tables intentionally kept `width: 100%`.

## Issue 3 — Contract Burn-Down panel stuck on "Loading…"
Two stacked bugs in the contract-drilldown endpoints:
1. **Date parameter binding** — `datetime.date` objects don't bind reliably through databricks-sql-connector's qmark interface; the second query threw on prepare.
2. **Invalid `MOD` syntax** — `fiscal_year MOD 100` (MySQL-style) is rejected by Databricks SQL.

Fix: rewrote all three endpoints to scope via a `WITH c AS (SELECT … WHERE contract_workspace_id = ?)` CTE + JOIN, so only `contract_id` (string) + `limit` (int) are bound. Changed `MOD` → `%`. Frontend added `burnDownError` state + error/empty/loaded render branches + `console.error` in all three `.catch` handlers.

## Issue 4 — Two more stacked bugs, exposed by the new error UI
1. **`TypeError: float / decimal.Decimal`** — `total_committed_spend` is `DECIMAL(18,2)` (returns `decimal.Decimal`); `cumulative_spend` was `float`. Fix: coerce `committed = float(...)` once before the loop.
2. **`ResponseValidationError: 73 errors`** — `fact_invoices.invoice_line_id` is `BIGINT` but `ContractInvoiceRow.invoice_line_id` is `str`. Fix: `CAST(i.invoice_line_id AS STRING)`. (`labeling.disagreements` has the same field but uses `response_model=list[dict]`, so pydantic skips validation — fragile.)

## Issue 5 — Home dashboard KPIs blank
`/api/kpis` threw `UNRESOLVED_COLUMN` on `source_pr_number` — the new `managed_spend_pct` assumed a PR column that doesn't exist on the invoice grain (actual schema has `po_matched_flag` + `source_po_header_id`). A second bug: the LEFT JOIN to `contract_inbound` fanned out for suppliers with overlapping contracts, pushing percentages above 100%.

Fix: rewrote `managed_spend_pct` (`po_matched_flag='Y' OR EXISTS(...)`) and `contract_coverage_pct` (`SUM(CASE WHEN EXISTS(...))`) to use `EXISTS` — true row-level boolean, never fans out.

**Warehouse-verified values at deploy:** Managed Spend **99.6%**, Contract Coverage **8.9%**, Total Spend **$2.91B** (T12M paid).
