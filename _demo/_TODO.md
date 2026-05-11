# TODO — Helios Finance Ecosystem Demo

> Tracks the work to complete the demo end-to-end. Phases mirror the design doc's build plan (Quick Wins → ML → Apps & Agents → Polish). Phase 0 is the in-progress foundation work that has to land before any Phase 1+ piece can run.
>
> Companion files: `00_design_context.md` (architecture), `data/generators/README.md` (data flow), root `README.md` (deploy commands).

---

## Phase 0 — Finish the foundation (in progress)

The DAB scaffold, data generators (anchor-driven, ML-ready), and stub pipeline SQL are committed. What's left to make the demo run end-to-end:

### Pipeline SQL — fill in stubs
- [ ] `pipelines/bronze/sap_ariba.sql` — 7 Auto Loader streaming tables reading from `/Volumes/${catalog}/${schema_raw}/${raw_volume}/sap_ariba/`: `LFA1_SUPPLIER_MASTER`, `EKKO_PO_HEADER`, `EKPO_PO_LINE`, `RBKP_INVOICE_HEADER`, `ARIBA_SOURCING_EVENT`, `ARIBA_CONTRACT_WORKSPACE`, `ARIBA_SUPPLIER_PERFORMANCE`. Glob `*_YYYYQq.csv` for per-quarter files.
- [ ] `pipelines/bronze/oracle_fusion.sql` — 10 Auto Loader streaming tables, mix of CSV + Parquet (per design context §3).
- [ ] `pipelines/bronze/inhouse_cms.sql` — 6 Auto Loader streaming tables reading line-delimited JSON.
- [ ] `pipelines/silver/*.sql` (10 files) — conformed canonical entities. Union across the three bronze sources where applicable; every row tagged with `source_system` / `source_table` / `source_primary_key`.
- [ ] `pipelines/gold/*.sql` (15 files) — facts + dims with Phase 2 hook columns reserved (`fact_spend.managed_spend_flag`, `.unspsc_segment_code`, `.unspsc_family_code`, `.supplier_canonical_id`, `.classification_confidence`; `dim_supplier.canonical_supplier_id`, `.entity_resolution_cluster_id`; `fact_revenue.contract_leakage_flag`, `.savings_realized_usd`).

### ML / governance notebooks — fill in stubs
- [ ] `ml/notebooks/01_extract_10q.py` — `ai_extract` / `AI_QUERY` over the filing HTML with a strict JSON schema → row per segment + CONSOL to `_meta.dim_period_anchors_draft` with `confidence_score`. Numbers extracted at source-filing scale (review step applies 1/10 + Helios rename).
- [ ] `ml/notebooks/02_review_anchor_draft.py` — interactive diff vs. prior quarter, segment→CONSOL tie-out, sign checks; on accept apply 1/10 + Helios rename, stamp reviewer fields, `MERGE` into `_meta.dim_period_anchors`.
- [ ] `ml/notebooks/03_regenerate_quarter.py` — sets `target_fiscal_year` + `target_fiscal_quarter` widgets and invokes the three source-file generators (`02_ariba_files.py`, `03_fusion_files.py`, `04_cms_files.py`).
- [ ] `ml/notebooks/99_validate_gold_vs_anchors.py` — for each anchor row, compute the matching aggregate from `gold.fact_revenue` / `gold.fact_spend`, assert within ±2% (raise on breach).

### First end-to-end run
- [ ] `databricks bundle validate -t dev` clean
- [ ] `databricks bundle deploy -t dev` succeeds
- [ ] Run `generate_data` job; verify `_meta.dim_period_anchors` seeded, files written to all three source subdirs, reconciliation gate (`99_reconcile.py`) passes ±2%
- [ ] Run `build_lakehouse`; verify bronze/silver/gold tables populated and `99_validate_gold_vs_anchors.py` passes
- [ ] Anonymization audit: `grep -r -i "honeywell\|HON\|Aerospace Technologies\|Industrial Automation\|Building Automation\|Energy and Sustainability"` against generated UC table contents (not just code)
- [ ] 10-Q replay smoke test: hand-craft a synthetic "next quarter" HTML, drop into `filings/raw/`, run `ingest_10q`, verify anchor row added + gold facts grow by one quarter and tie out

### Operational
- [ ] Reconcile workspace target with the recently-edited `databricks.yml` (now uses `profile: DEFAULT` for both `dev` and `prod`, host `e2-demo-field-eng`). Decide if a separate prod workspace is still wanted.
- [ ] Decide on git remote (GitHub org? branch protection?)

---

## Phase 1 — Quick Wins (per design doc — Sprint 0)

- [ ] Genie space configuration as DAB resource (or one-shot notebook) — auto-create, attach metric views, publish.
- [ ] Managed spend metric: derive `managed_spend_flag` on `fact_spend` from PO compliance signals (has matching PO, has matching contract, supplier is in approved master).
- [ ] UNSPSC taxonomy: pick version (UNSPSC 25.0 recommended), populate `gold.dim_unspsc_taxonomy` from the public ZIP. Open question from design doc: real UNSPSC vs synthetic taxonomy.
- [ ] Port metric views from old `fin_demo`: cash_obligations, revenue_growth, headcount, fpa_planning. Update to read from new gold tables.
- [ ] Add new metric views: managed_spend, tail_spend, category_coverage, PO_compliance.
- [ ] Port AI_FORECAST + AI_QUERY queries from old demo (`03.Queries/`).
- [ ] Port FinOps + Executive dashboards as Lakeview JSON under `dashboards/`; update queries to new schemas.
- [ ] Add new dashboard: Managed Spend Visibility (exec-facing, single page).

---

## Phase 2 — ML Use Cases (per design doc — Sprint 1)

> Training data is already embedded in `bronze_ariba.EKPO_PO_LINE._true_spend_category` (see `data/generators/README.md` § "Spend classification — what's in the data for ML").

- [ ] Spend classification model — MLflow pipeline.
  - Features: `TXZ01` (text), `LIFNR` + supplier metadata, `MATGROUP` (noisy), `NETWR`, `cost_center`, `BUKRS`/segment.
  - Label: `_true_spend_category` (held in bronze, joinable through silver).
  - Headline metric: top-1 accuracy on a held-out set; secondary metric: top-1 accuracy on the **maverick slice** (suppliers with `_maverick_propensity > 0.15`).
  - Register model to UC; surface predictions back to `fact_spend.unspsc_family_code` + `.classification_confidence`.
- [ ] Supplier entity resolution: rules-based fuzzy match across Ariba `LFA1` + Fusion `ap_supplier_sites_all` → populate `dim_supplier.canonical_supplier_id` + `entity_resolution_cluster_id`. Add Soundex / token-set / address-similarity features.
- [ ] Contract leakage detection: SQL view comparing PO spend vs `contract.commercial_terms` / `ARIBA_CONTRACT_WORKSPACE.TotalCommittedSpend`; flag off-contract spend → `fact_spend.contract_leakage_flag`.
- [ ] Savings tracking: negotiated vs captured by category/supplier — requires sourcing-event award data (already in `ARIBA_SOURCING_EVENT.AwardedAmount`). Populate `fact_revenue.savings_realized_usd` and a parallel `fact_spend.savings_captured_usd`.

---

## Phase 3 — Apps & Agents (per design doc — May–June)

- [ ] Lakebase Supplier Master app (FastAPI + React) — see `dbx-app-fastapi-react` skill. CRUD for category managers to correct supplier variants, with audit trail written back to UC.
- [ ] Maverick spend anomaly detection — ML model trained on amount / category / supplier pattern; alerts when a PO line is statistically off-pattern.
- [ ] Autonomous agents (Mosaic AI Agent Framework):
  - Spend monitoring agent (proactive alerts when category spend trends off).
  - Leakage alerter (notifies when off-contract spend crosses a threshold).
  - Consolidation recommender (suggests supplier rationalization based on overlap).

---

## Phase 4 — Polish & Package (pre-DAIS, June)

- [ ] Demo script storyboard (new — old one in old fin_demo as `FINANCE_DEMO_SCRIPT_OLD.md` for reference).
- [ ] Pitch deck (≤ 8 slides + architecture diagram). Wave Plan definition-of-done requirement.
- [ ] Demo video (3–5 minutes portable recording). Wave Plan definition-of-done requirement.
- [ ] dbdemos packaging — Gold-tier requirements (per design doc § 5):
  - [ ] DAB-ified install into any workspace
  - [ ] Notebook standards: ≤10 cells, ≤10 lines per cell, prefer SQL, top-of-notebook diagram, reset widget, `_resources/00-setup`, Google Analytics tracking pixel
  - [ ] RUNME notebook
  - [ ] Architecture diagram in README
  - [ ] BYOD migration guide
  - [ ] Teardown notebook
  - [ ] Lakehouse platform pitch visual in first notebook
- [ ] CI in `databricks-industry-solutions` repo (notebooks run on `e2-demo-field-eng` per PR).
- [ ] FEIP ticket (go/feip/board) for PERF tracking.
- [ ] Demo Review Document (DRD): storyline, timeline, manager + Lead SA approval.
- [ ] Fork `dbdemos-notebooks`, branch, submit PR (reviewers: Cal Reynolds / Quentin Ambard).
- [ ] Submit to demo catalog (go/demo-catalog).

---

## Open questions (carried from design doc + scaffold decisions)

- [ ] **UNSPSC taxonomy** — real UNSPSC 25.0 (~150K codes) or synthetic 30-category mapping that matches `_lib.SPEND_CATEGORIES`? Real is more credible; synthetic is faster.
- [ ] **Lakebase app placement** — standalone app under `apps/supplier_master/` or embedded in the demo flow?
- [ ] **"Databricks on Databricks" angle** — retain from old script or drop?
- [ ] **ML SME** — design doc named TBD (1 ML person/wave). Without one, Phase 2 ML model is "best effort" rather than headline.
- [ ] **FEIP timing** — file in Sprint 0 or Sprint 1?
- [ ] **Reference-filing privacy** — keep source filer name fully scrubbed (current state) or document privately in a non-committed notes file? Current scaffold removes from all committed artifacts.
- [ ] **Schedule for `generate_data`** — initial scaffold has none (one-time-ish). Decide if a monthly schedule for re-randomization would keep the demo fresh.

---

## Verification checklist (run after Phase 0 completes)

End-to-end smoke test (per `_demo/00_design_context.md` § 7):

1. [ ] `_meta.dim_period_anchors` has rows for FY2023, FY2024, Q1'25 → Q3'25 with `human_reviewed_by = 'SEED'`.
2. [ ] Catalog explorer shows `bronze_ariba` / `bronze_fusion` / `bronze_cms` with source-shaped table names.
3. [ ] `/Volumes/finance_demo/raw_data/files/sap_ariba/EKPO_PO_LINE_2024Q3.csv` exists; ditto Fusion (.parquet/.csv) and CMS (.jsonl).
4. [ ] Reconciliation gate (`99_reconcile.py`) passes for every (fy, fq, segment).
5. [ ] 10-Q replay: drop synthetic "next quarter" HTML → `ingest_10q` → quarter added → `build_lakehouse` → gold grows by one quarter and `99_validate_gold_vs_anchors.py` passes.
6. [ ] Anonymization audit: zero hits for the source filer name / original segment names anywhere in generated UC table content or committed files.
