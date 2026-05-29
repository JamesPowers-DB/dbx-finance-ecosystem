# Open questions (carried)

- [ ] **UNSPSC taxonomy** — real UNSPSC 25.0 or synthetic 30-category mapping? (Locks how the ML model's predictions encode `unspsc_family_code`.)
- [x] **Lakebase app placement** — standalone project (`projects/helios-sourcing`), not embedded. OBO per-request; no shared pool.
- [ ] **"Databricks on Databricks" angle** — retain from old script or drop.
- [ ] **ML SME** — design doc named TBD. Without one, Phase 2 ML is "best effort" rather than headline.
- [ ] **FEIP timing** — Sprint 0 or Sprint 1.
- [ ] **Reference-filing privacy** — keep scrubbed or document privately.
- [ ] **Schedule for `generate_data`** — one-time or monthly re-randomization.

## Foundation verification checklist (run after build_lakehouse)
1. [x] `_meta.dim_period_anchors` has FY2023, FY2024, Q1'25 → Q3'25.
2. [x] `gold.fact_invoices` populated (312,188 rows, FY23–FY26 Q1); `dim_supplier` (3,000); `silver.contract_inbound` (896 active).
3. [ ] `gold.fact_fpa_actuals` totals reconcile to anchors per (fy, fq, segment) within ±2%.
4. [x] Reconciliation gate (`99_reconcile.py`) passes for raw files.
5. [ ] Anonymization audit: zero hits for source filer name / original segment names in UC table content.
6. [x] `ml.invoice_classifications` fully populated (312,188 rows); `fact_invoices.predicted_secondary_category` non-NULL for all rows.
