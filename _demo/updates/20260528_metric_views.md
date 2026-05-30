# 2026-05-28 — App review, TODO restructure, metric layer (spend + parties)

## App review (apps/spend-analytics)
Reviewed the returned app. Strong work; the 2026-05-27 defensibility pass already fixed the worst metric bugs. Key remaining finding: **metrics aren't standardized** — hand-written SQL in router strings, same concept redefined with drift (two `pct_consumed` definitions; chatbot "total spend" diverges from Home because Genie writes its own SQL with no PAID/T12M filter; Home fires 3 full-scan T12M queries; `measured_maverick_pct` duplicated). Minor non-breaking cleanups logged in [phase3_apps.md](../todo/phase3_apps.md) (local HTTPException imports, histogram float labels, GROUP BY COALESCE, DDL-on-first-request comment).

## TODO restructure
Split the 652-line `_TODO.md` into a 49-line index + `todo/` aspect files + `updates/` dated session logs (this file is one). Format for future updates: `updates/YYYYMMDD_{feature}.md`, one per session.

## Metric layer — spend + parties (build + validate)

Redefined **Managed Spend** after the live numbers told a contradictory story (managed 99.6% / contract 8.8%):
- Old `po_matched OR contract` pegged at 99.6% (every invoice has a PO → no story).
- New **`contracted OR competitively-sourced`** = **50.2%**. PO-match split out as a separate "PO Coverage" AP-hygiene metric (99.6%, honest).

Built two subject-scoped metric views (validated live in `horizontal_finance_dev.gold`):
- **`gold.mv_spend`** (base) — `source:` is a SQL query computing the governed per-line flags once; all spend measures + dims.
- **`gold.mv_supplier_performance`** (nested on `mv_spend`) — supplier scorecard; inherits flag logic, ratios re-aggregate correctly through nesting.

No semantic/materialized view needed (metric views accept a SQL-query source and nest). IaC: `metric_views/apply_metric_views.py` + `jobs/apply_metric_views.yml` (metric views can't be Lakeflow pipeline datasets, so they apply via a post-pipeline job). Bundle validates.

Refined same session: `dim_supplier` moved to a declarative metric-view `join` (`rely: at_most_one_match`, no fan-out, verified); contract/sourcing kept as `EXISTS`/`IN` (many-per-supplier — a LEFT join inflates measures). Ratio measures now stored as **natural fractions** with `format: percentage` (and `format: currency` for spend); `comment` + `synonyms` added to every measure + key dimension for Genie/AI metadata.

Detail + remaining work (router refactor held for go-ahead; Genie repoint; revenue/accounting/legal subjects) in [todo/metric_views.md](../todo/metric_views.md).
