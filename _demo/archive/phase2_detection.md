> ✅ **COMPLETED — archived 2026-06-04.** The project shipped to its final production
> demo environment (catalog `manufacturing`, workspace `fevm-mfg-industry-prod`) with a
> self-refreshing weekly data job. Retained for historical context; checklist items are
> marked done. Current state lives in the repo `README.md`.

# Phase 2 — Remaining ML / SQL detection

> After the spend classifier.

- [x] Supplier entity resolution (rules-based fuzzy match) → populate `dim_supplier.canonical_supplier_id` (currently identity).
- [x] Contract leakage detection (SQL view comparing spend vs `silver.contract_inbound`).
- [x] Savings tracking (negotiated vs captured by category/supplier; uses sourcing-event award data). Auto-detected reductions already in `gold.fact_cost_savings`; this extends to leakage/realization analysis.
