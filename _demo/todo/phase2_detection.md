# Phase 2 — Remaining ML / SQL detection

> After the spend classifier.

- [ ] Supplier entity resolution (rules-based fuzzy match) → populate `dim_supplier.canonical_supplier_id` (currently identity).
- [ ] Contract leakage detection (SQL view comparing spend vs `silver.contract_inbound`).
- [ ] Savings tracking (negotiated vs captured by category/supplier; uses sourcing-event award data). Auto-detected reductions already in `gold.fact_cost_savings`; this extends to leakage/realization analysis.
