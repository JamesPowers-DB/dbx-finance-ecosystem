# 2026-05-28 — Procurement document lineage (contracts & sourcing events → invoices)

## Why
The metric layer answered "is this spend contracted / competitively sourced?" with **supplier-level heuristics** (`is_sourced` = supplier won *any* event → one award flagged 100% of their spend; `is_contract_matched` = EXISTS a supplier+date-overlapping contract). That — not a query bug — was the root cause of the contradictory live numbers (8.8% contracted / 99.6% managed). There were **no lineage keys** connecting `contract_inbound` / `sourcing_event` to invoices; the only join was `supplier_id`.

## What changed — model the real procure-to-pay flow
Stamp an origination channel on every PR and link it to a contract and/or sourcing event by **value threshold + imperfect compliance**, then let those references ride the existing PR→PO→invoice line propagation.

- **`pr_source`** (PR header→line): `Catalog` / `AribaPortal` / `ManualSubmission` / `ProcurementAgent`. All PRs land in Ariba; this is where they *originated*. Tilted by dollar size, category routineness, and supplier maverick propensity. Non-PO direct vouchers carry NULL ("Non-PO Voucher").
- **Thresholds (independent, soft-jittered):** PR value > $50K ⇒ contract expected; > $500K ⇒ sourcing event expected. Sampled independently → all four quadrants (both / contracted-only / sourced-only / unmanaged).
- **Compliance is the story:** per-source probabilities (e.g. ManualSubmission under-complies → off-contract leakage; Catalog over-complies → pre-negotiated catalog contracts). Chaos via exception flips + per-line dropout (mixed PRs).
- **Linkage = lookup-or-mint:** link to an existing active contract/awarded event for the supplier covering the PR date; mint one on demand if none exists, so every *intended* link resolves (managed rate is **authored**, not capped by base coverage). Base contracts/events that never get linked still exist.

## Where
- **`data/generators/_lib.py`** — thresholds, `PR_SOURCES` + base weights, `SOURCE_COMPLIANCE`, `ROUTINE_CATEGORIES`, chaos knobs.
- **`02_ariba_files.py`** — contracts/events now in-memory **registries** (built before the quarter loop, mutated by a per-quarter lineage pass, written after). New `_assign_pr_source` + lookup/mint helpers. Lineage stamped on PR lines post-renorm.
- **`03_fusion_files.py`** — `_pr_source` / `_contract_id` / `_sourcing_event_id` propagate PR→PO→invoice line; NULL on non-PO vouchers; added to `ap_line_schema` + PO-lines cast.
- **`99_reconcile.py`** — check (7): FK integrity (STRICT) + story telemetry (Managed/Contracted/Sourced by $ vs count, `pr_source` mix).
- **silver** `purchase_request` / `purchase_order` / `invoice_ap`; **gold** `fact_purchase_requests` / `fact_purchase_orders` / `fact_invoices` — project the three columns. `fact_invoices.contract_id → contract_inbound.contract_workspace_id`, `sourcing_event_id → sourcing_event.event_id`.
- **`metric_views/apply_metric_views.py`** — `mv_spend` flags are now `contract_id IS NOT NULL` / `sourcing_event_id IS NOT NULL` (**EXISTS/IN semi-joins retired**). New dims `PR Source`, `Managed Status`; new measures `Managed Spend` / `Unmanaged Spend` ($), and `… Pct (count)` companions to show the dollar-vs-count divergence. Nested supplier view gains Managed Spend / Pct.

## Key downstream property
Managed/contracted/sourced spend is now a **small count of large dollars** — high $-coverage, much lower count-coverage. Metrics are dollar-weighted; count companions expose the gap. Totals are unchanged (lineage is metadata; invoice-amount renormalization untouched) so the ±2% anchor tie-out still holds.

## Status / next
- ⏳ **Regen + full pipeline refresh + re-apply metric views**, then re-validate the headline numbers (target Managed ≈ 50% by $). Compliance probabilities in `_lib.SOURCE_COMPLIANCE` are the tuning knob.
- Invoice spend **categorization** (ML) explicitly deferred — user has separate notes.
- App router refactor + Genie repoint still held.
