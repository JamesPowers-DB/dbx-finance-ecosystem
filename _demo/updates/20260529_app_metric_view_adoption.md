# 2026-05-29 — App + Genie adopt the metric views; Spend Analytics dashboard; bug cleanups

The app and Genie now consume the governed metric views (gold.mv_spend,
gold.mv_supplier_performance) instead of hand-written, drifting SQL. Four workstreams:

## A. Router refactor onto the metric views
- **`system.py /api/kpis`** — three full-scan queries collapsed to one `mv_spend`
  query (`MEASURE(...) … GROUP BY ALL`, ratios ×100 to keep the percent-number API
  contract). **Managed Spend is now lineage-true (~50.6%)** vs the old 99.6%
  PO-or-contract heuristic.
- **`suppliers.py`** — `_supplier_t12m_agg_sql` replaced by `_mvsp_inner_sql` over
  `mv_supplier_performance` (wrapped as a subquery so list/scorecard/renegotiation
  filter & sort on the result). category_breakdown + spend_trend now hit `mv_spend`.
  Dropped the unused `country_code` field (type made optional).
- **`chatbot.py`** — `suggest_supplier` maverick subquery → `mv_supplier_performance`
  (consolidates the duplicate maverick definition; dropped the rarely-used segment filter).
- Tooltips (`metricDefinitions.ts`) + Home "Managed Spend" sub-text updated to
  "contracted or sourced". Grant not needed (views owned by the demoer; OBO reads as owner).

## B. New Spend Analytics dashboard
- **Backend** `routers/analytics.py`: `/api/analytics/spend_composition` (by category /
  segment / pr_source), `/managed_status` (4 quadrants + $-vs-count headline),
  `/spend_trend` (by fiscal quarter), `/supplier_concentration` (top-N + cumulative %).
- **Frontend** `pages/Analytics.tsx` + nav entry; new `charts/SpendTrendChart.tsx`
  (two-series line+area). Reuses BarChart / StatTile / Card / SegSelect.

## C. Genie repointed
- `Strategic Spend Analytics` space (01f154f176351736be32d20533d9f257) now includes
  `gold.mv_spend` + `gold.mv_supplier_performance` (10 tables total) with steering
  instructions: "use MEASURE() on the metric views for spend totals/rates; never
  SUM(fact_invoices.amount)." Verified — Genie answers "total / managed spend" with
  `MEASURE(total_spend)/MEASURE(managed_spend_pct) FROM mv_spend` → $2.96B / 50.6%,
  matching the app exactly (the "total spend" divergence is gone). No app code change.

## D. Bug cleanups (from phase3_apps.md)
- `HTTPException` moved to module top in contracts/suppliers/labeling (removed ~9 in-body imports).
- labeling confidence histogram bucket labels rounded (no more `0.30000000000000004`).
- cost_savings summary `GROUP BY COALESCE(segment_code,'Unknown')` to match the SELECT.

## Validation
KPI / supplier / analytics queries parity-checked against the views via SQL; frontend
`tsc` clean; backend `py_compile` clean; Genie verified. Local dev-loop + deploy smoke
still to run (app block in `resources/apps.yml` is commented out — un-comment before deploy).
