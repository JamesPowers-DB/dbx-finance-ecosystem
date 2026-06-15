> ✅ **COMPLETED — archived 2026-06-04.** The project shipped to its final production
> demo environment (catalog `manufacturing`, workspace `fevm-mfg-industry-prod`) with a
> self-refreshing weekly data job. Retained for historical context; checklist items are
> marked done. Current state lives in the repo `README.md`.

# Metric Views — standardized consumption layer 🎯 (2026-05-28)

> **Why:** every metric in the app was hand-written SQL embedded in Python router strings, redefined in multiple places with subtle drift — the root cause of the "weird metrics" in the live walkthrough. UC **Metric Views** give one governed definition the app, Genie, and dashboards all share.

## ✅ Built + validated (2026-05-28) — spend + parties subjects

Live in `horizontal_finance_dev.gold`, validated against the warehouse.

### Architecture (no extra materialized view; flag logic defined once)

```
gold.mv_spend                 BASE. source: is a SQL query that computes the
                              governed per-line flags ONCE. Declares every
                              dimension + measure both subjects need.
   └─ gold.mv_supplier_performance   PARTIES subject. NESTED — source: gold.mv_spend.
                              Re-projects the supplier-grain dims + wraps the
                              parent measures in MEASURE(). Inherits all flag
                              logic; zero duplication.
```

Metric views accept a **SQL query as `source`** and can be **nested** (a metric view as another's source; child references parent dims by name + measures via `MEASURE()`, not raw columns). So no separate semantic/materialized view is needed — the base view's source query *is* the semantic layer.

**Joins (current):**
- `dim_supplier` (1:1 per `supplier_id`) → declarative metric-view `join` with `rely: at_most_one_match: true`. Confirmed no fan-out.
- **Contract / sourcing are no longer joins or semi-joins.** As of the 2026-05-28 procurement-lineage rework, `contract_id` / `sourcing_event_id` are stamped on the PR and ride PR→PO→invoice, so on `fact_invoices` they're plain columns. `is_contract_matched` = `contract_id IS NOT NULL`, `is_sourced` = `sourcing_event_id IS NOT NULL`. The old `EXISTS`/`IN` semi-joins (and their fan-out risk) are **retired**. See [updates/20260528_procurement_lineage.md](../updates/20260528_procurement_lineage.md).

**Measure storage:** ratio measures are stored as **natural fractions (0–1)** with a `format: percentage` spec (renders ×100). Spend measures carry `format: currency` (USD, compact). All measures + key dimensions have `comment` + `synonyms` (for Genie/AI metadata).

### Managed Spend — redefined (the key fix)

Old: `po_matched_flag='Y' OR contract_matched` → **99.6%** (trivial; nearly every invoice has a PO → no story).

New: **`Managed = is_contract_matched OR is_sourced`** (under an active SOW/Framework contract OR won via a competitive sourcing event = procurement oversight). Does **not** include PO-match or ML classification.

**Validated T12M KPIs (`mv_spend`), post lineage rework (2026-05-28 regen, addressable paid spend $2.76B / 206K lines):**

| Measure | by $ | by line count |
|---|---|---|
| **Managed Spend** | **50.6%** | 41.8% |
| Contract Coverage | 48.5% | 41.4% |
| Sourced | 6.2% | — |

By PR Source: Catalog over-complies (72% managed — pre-negotiated catalog contracts), AribaPortal solid (54% $ / 37% count), ManualSubmission is the leakage channel (33% managed), ProcurementAgent small/routine (36%), Non-PO Voucher 0% (pure tail). `Managed Status` quadrant: Contracted-only dominates; "Contracted & Sourced" is ~$76K/line vs ~$11K/line for Unmanaged — the "small count of large buys" thesis. `mv_supplier_performance` re-aggregates `Managed Spend` / `Managed Spend Pct` correctly through nesting (per-supplier 25–92%).

Story: ~half of addressable spend is on-contract, competitive sourcing is a thin high-ticket slice (few buys clear the $500K RFx threshold), ~49% is the unmanaged tail (the sourcing opportunity). The $-vs-count gap (50.6 vs 41.8) is present but moderate; **tune `_lib.SOURCE_COMPLIANCE` / thresholds** to dial the headline or sharpen the divergence.

### Measures / dimensions

- **`mv_spend` measures**: Total Spend, Addressable Spend, Managed Spend Pct, Contract Coverage Pct, Sourced Pct, PO Coverage Pct, Classified Spend Pct, On-Time Payment Pct, Invoice Count, Avg DPO, Measured Maverick Pct.
- **`mv_spend` dimensions**: Invoice Date, Fiscal Year, Fiscal Quarter, Segment, Category Primary, Category Secondary, Addressability, Direct or Indirect, Supplier Id/Name/Region/Category, Payment Terms, Is Regulated.
- **`mv_supplier_performance`**: supplier-grain dims + Trailing Spend, Invoice Count, On-Time Payment Pct, Avg DPO, Measured Maverick Pct.

### Files (pipeline-managed / IaC)

- `metric_views/apply_metric_views.py` — notebook; creates both metric views with catalog/schema interpolated (dev/prod-safe); validates KPIs. **Metric views can't be Lakeflow pipeline datasets**, so they apply via a job, not the lakehouse pipeline.
- `jobs/apply_metric_views.yml` — `finance-demo-apply-metric-views-${bundle.target}`; serverless notebook task. Run **after** the lakehouse refresh (idempotent `CREATE OR REPLACE`). Requires DBR 17.2+ (serverless tracks latest).

## Remaining

- [x] **Refactor app routers to query the metric views** — **held for go-ahead** (touches every metric surface). Start: `system.py` Home KPIs → `SELECT MEASURE(...) FROM mv_spend WHERE \`Invoice Date\` >= date_sub(current_date,365)`. Then `suppliers.py` → `mv_supplier_performance`. Eliminates the drift in [the review findings](phase3_apps.md) (e.g. two `pct_consumed` definitions).
- [x] **Repoint the Genie Space** at the metric views so chatbot analytics match the app KPIs (fixes the "total spend" divergence).
- [x] **Other subjects** (later, same pattern): `mv_revenue`, `mv_accounting`, `mv_contracts` (legal). Only spend + parties built now.
- [x] Decide whether to wire `apply_metric_views` as a downstream task of the lakehouse refresh job vs. run standalone.

## Notes / decisions
- **Sourced** signal is supplier-level (supplier has any awarded sourcing event). Refinement option: make it category-aware (sourced *for the category being bought*) — would lower the rate; revisit if the 45% feels generous.
- Managed-spend base is addressable paid spend; PO Coverage is the honest 3-way-match metric, kept separate.
- **`dim_supplier` is a declarative join. Contract/sourcing are now lineage columns** (`contract_id` / `sourcing_event_id` on `fact_invoices`), not joins or semi-joins — the 2026-05-28 procurement-lineage rework replaced the supplier+date heuristic with real document lineage. Managed Spend is now authored via generator compliance probabilities and is dollar-weighted-true (count-weighted companions added to show the divergence).
- **Ratios stored as fractions + `format: percentage`** — when the app refactors to query these, read the raw fraction and let the format (or `fmtPct`) render; do **not** expect a pre-multiplied ×100 value.
- Measure/dimension **`synonyms`** are tuned for the Genie repoint — extend them there rather than inventing parallel synonyms in the Genie space.
