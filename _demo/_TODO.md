# TODO — Helios Finance Ecosystem Demo

> Tracks the work to complete the demo end-to-end. Pivoted: the ML spend-classification model is now the headline capability. Consumption surfaces (dashboards, Genie) are deferred behind it.
>
> Companion files: `00_design_context.md` (architecture), `data/generators/README.md` (data flow), `README.md` (deploy commands).

---

## 📍 Status snapshot (as of 2026-05-11)

**Working end-to-end:**
- ✅ DAB scaffold + direct deployment engine + `test_` name_prefix preset for dev
- ✅ Generators run as serverless notebook tasks; raw files for FY23, FY24, Q1-Q3 2025
- ✅ Reconciliation gate (`99_reconcile.py`) passes ±2% / strict GL balance
- ✅ Pipeline SQL implemented end-to-end — 28 files, ~1000 lines
  - 3 bronze (`sap_ariba`, `oracle_fusion`, `inhouse_cms`)
  - 10 silver (canonical conformed entities)
  - 15 gold (facts + dims with Phase 2 ML hooks reserved)
- ✅ Codebase parameterized — no hardcoded catalog/schema/volume names on the deploy path

**Next immediate steps (in order):**
1. **Deploy and run `build_lakehouse`** — verify all bronze/silver/gold tables populate, gold-vs-anchor validator passes.
2. **Start the ML spend-classification work** — the headline of the demo, per the design doc.

---

## Phase 0 — Finish the foundation

### Pipeline SQL — DONE ✅
- [x] `pipelines/bronze/sap_ariba.sql` — 7 Auto Loader streaming tables.
- [x] `pipelines/bronze/oracle_fusion.sql` — 11 streaming tables (CSV + Parquet).
- [x] `pipelines/bronze/inhouse_cms.sql` — 6 streaming tables (line-delimited JSON).
- [x] `pipelines/silver/*.sql` — 10 conformed entities as materialized views, source-tagged.
- [x] `pipelines/gold/*.sql` — 15 facts/dims with Phase 2 hooks reserved on `fact_spend`, `dim_supplier`, `fact_revenue`.

### Build the lakehouse — NEXT
- [ ] `DATABRICKS_BUNDLE_ENGINE=direct databricks bundle deploy -t dev`
- [ ] `databricks bundle run build_lakehouse -t dev` — should populate all bronze/silver/gold tables incrementally.
- [ ] Quick sanity checks in SQL editor:
  ```sql
  SELECT COUNT(*) FROM test_finance_demo.gold.fact_spend;       -- expect ~750k rows
  SELECT COUNT(DISTINCT po_number) FROM test_finance_demo.gold.fact_spend;
  SELECT segment_code, fiscal_year, fiscal_quarter, SUM(extended_amount)
    FROM test_finance_demo.gold.fact_spend
    GROUP BY segment_code, fiscal_year, fiscal_quarter ORDER BY 2, 3, 1;
  ```
- [ ] Implement `ml/notebooks/99_validate_gold_vs_anchors.py` (currently stub) — assert gold totals tie back to `_meta.dim_period_anchors` ±2%. Wired as the final task in `build_lakehouse.yml`.

### 10-Q ingestion notebooks (still stubs)
- [ ] `ml/notebooks/01_extract_10q.py` — `ai_extract` over filing HTML → draft anchor row.
- [ ] `ml/notebooks/02_review_anchor_draft.py` — human-in-the-loop diff + MERGE.
- [ ] `ml/notebooks/03_regenerate_quarter.py` — quarter-scoped generator re-run.
- [ ] 10-Q replay smoke test (synthetic HTML drop → ingest_10q → quarter added → build_lakehouse → validator passes).

### Smoke tests
- [ ] Anonymization audit: grep all UC table contents (not just code) for source filer name / original segment names.

### Operational / dev experience — deferred
- [ ] **Per-user dev resource naming.** Today the dev target uses `mode: production` + `${bundle.target}` suffix → resources land as e.g. `finance-demo-generate-data-dev`. Preferred convention is `[dev <user>] finance-demo-generate-data` style (matches DAB's `mode: development` auto-prefix output) so ownership is visible in the Workflows / Pipelines UI and multiple developers can deploy concurrently without name collisions on dev.
  - Why deferred: `mode: development` was the source of the state-drift corruption we just escaped. Need a stable approach that gives the `[dev <user>]` prefix without reintroducing the state-management pain.
  - Options to evaluate when we tackle this:
    1. Use `${workspace.current_user.short_name}` literally in resource `name:` fields under the dev target — same effect as the auto-preset, but deterministic and visible in YAML.
    2. Re-enable `mode: development` with a strict policy (never change naming-related config mid-cycle; always `bundle destroy` before reconfig).
    3. Per-user catalog override (e.g., `horizontal_finance_${workspace.current_user.short_name}_dev`) so dev resources are namespaced per developer at the data layer too.
  - Acceptance: two developers can `bundle deploy -t dev` from their own machines simultaneously without overwriting each other's jobs / pipelines / catalog.

### Done ✅
- [x] DAB scaffold (`databricks.yml`, `resources/`, `jobs/`, `pipelines/`).
- [x] Resolve direct-deployment-engine requirement for catalog resources.
- [x] Parameterize all code-path references.
- [x] `name_prefix: "test_"` preset on dev.
- [x] `requirements.txt` + `environments` block on every job.
- [x] Self-healing `ensure_volume()` helper.
- [x] `databricks bundle validate -t dev` clean.
- [x] `databricks bundle deploy -t dev` succeeds.
- [x] `generate_data` runs end-to-end; anchors seeded; raw files materialized; reconciliation passes.
- [x] All 28 pipeline SQL files implemented (bronze + silver + gold).
- [x] Scrub source-filer name references from committed artifacts.

---

## 🎯 ML spend classification (headline of the demo)

> Goal: build an MLflow-tracked model that classifies a PO line into one of 30 spend categories from its description + supplier + amount + GL coordinates — so sourcing organizations can segment their sourcing strategies (consolidate suppliers in high-spend categories, flag maverick spend, focus negotiations).
>
> Training data is already prepared. `gold.fact_spend.true_spend_category` is the supervised label; features are in the same row plus `dim_supplier`. ~750K labeled PO lines across 30 categories with intentional drift (8% MATGROUP noise, 6% maverick spend) that makes the problem non-trivial.

### Step 1 — Feature engineering
- [ ] `ml/notebooks/spend_classification/00_prep_training_data.py` — pulls features from `gold.fact_spend` joined with `dim_supplier`, splits train/holdout (80/20 stratified by category, plus a separate **maverick slice** where `supplier_maverick_propensity > 0.15`). Writes:
  - `<catalog>.ml.spend_clf_train` — features + label
  - `<catalog>.ml.spend_clf_holdout` — holdout
  - `<catalog>.ml.spend_clf_maverick_holdout` — hard-case eval slice
- [ ] Feature set:
  - **Text**: `line_description` (TXZ01)
  - **Categorical**: `supplier_id`, `material_group_code`, `segment_code`, `po_doc_type`, `supplier_segment_affinity`, `supplier_region`
  - **Numeric**: `extended_amount` (log-scaled), `quantity` (log-scaled), `unit_price` (log-scaled)
  - **Derived**: `is_high_maverick` (= supplier_maverick_propensity > median), `is_cross_segment_supplier`

### Step 2 — Baseline model
- [ ] `ml/notebooks/spend_classification/01_train_baseline.py` — TF-IDF (line_description) + one-hot + LightGBM multi-class classifier. Hyperparameters: 30 classes, depth ≤ 8, ~500 trees. MLflow autolog. Target: ≥85% top-1 accuracy on holdout.
- [ ] Register the baseline model to UC: `<catalog>.ml.spend_classifier`. Tag with `stage = challenger`.

### Step 3 — Foundation-model variant (optional, but a Databricks showcase)
- [ ] `ml/notebooks/spend_classification/02_train_fmapi.py` — uses Foundation Model API (databricks-bge-large-en) to embed `line_description`, then a small classifier head on the embedding + tabular features. Compare to baseline.

### Step 4 — Evaluation
- [ ] `ml/notebooks/spend_classification/03_evaluate.py` — three reports:
  1. Holdout top-1 accuracy + per-category F1 (confusion matrix).
  2. Maverick-slice accuracy (model has to overcome the 6% noise).
  3. Beat-MATGROUP-alone baseline: how much does the model improve over predicting `MATGROUP → category` lookup?
- [ ] Promote the winning model to `stage = production` in UC.

### Step 5 — Batch inference back to gold
- [ ] `ml/notebooks/spend_classification/04_batch_inference.py` — loads production model, scores all `fact_spend` rows, writes predictions back to `fact_spend.unspsc_family_code` + `.classification_confidence` + `.managed_spend_flag` (derive from confidence + PO compliance signals).
- [ ] Wire as a new task in a `jobs/score_spend.yml` job that runs after `build_lakehouse`.

### Step 6 — Model serving (optional)
- [ ] Create UC-registered-model-backed serving endpoint for real-time classification (e.g., used by a Lakebase Supplier Master app for inline category suggestions when manually correcting supplier records).

### Step 7 — Sourcing-strategy outputs
- [ ] `<catalog>.gold.vw_sourcing_strategy` — gold view that joins `fact_spend` (now with classified categories) with `dim_supplier` and outputs:
  - Category × segment × supplier-share table (concentration / tail-spend by category)
  - Top maverick offenders per category
  - Off-contract category spend (joined with `silver.contract_inbound`)
- [ ] One Lakeview tile or a Genie space (later) on top of this view.

### Open ML questions
- [ ] **UNSPSC mapping** — should `unspsc_family_code` actually be UNSPSC codes (real taxonomy) or our internal 30-category code? Design doc says "85% auto-classification accuracy to UNSPSC". Simplest: 1:1 map from our 30 categories to a chosen UNSPSC family code each.
- [ ] **Model framework** — LightGBM (interpretable, fast) vs. neural net on FMAPI embeddings (showcase). Could do both and compare.
- [ ] **Confidence threshold** for `managed_spend_flag`: probably 0.75+ counts as "managed".

---

## Phase 1 — Quick Wins (consumption surfaces) — DEFERRED behind ML

> Returns to focus after ML pipeline lands. Not blocked on ML; can interleave.

- [ ] Genie space configuration as DAB resource.
- [ ] Managed spend metric derivation (now plug into ML output via `fact_spend.managed_spend_flag`).
- [ ] UNSPSC taxonomy dim — depends on decision in ML open question.
- [ ] Port metric views from old `fin_demo`.
- [ ] Add new metric views: managed_spend, tail_spend, category_coverage, PO_compliance.
- [ ] Port AI_FORECAST + AI_QUERY queries.
- [ ] Port FinOps + Executive dashboards.
- [ ] Add new dashboard: Managed Spend Visibility.

---

## Phase 2 — Remaining ML / SQL detection — AFTER spend classifier

- [ ] Supplier entity resolution (rules-based fuzzy match) → populate `dim_supplier.canonical_supplier_id`.
- [ ] Contract leakage detection (SQL view comparing spend vs `contract_inbound`).
- [ ] Savings tracking (negotiated vs captured by category/supplier; uses sourcing-event award data).

---

## Phase 3 — Apps & Agents

- [ ] Lakebase Supplier Master app (FastAPI + React, see `dbx-app-fastapi-react` skill).
- [ ] Maverick spend anomaly detection (separate model, on top of classification output).
- [ ] Autonomous agents (Mosaic AI Agent Framework): spend monitoring, leakage alerter, consolidation recommender.

---

## Phase 4 — Polish & Package (pre-DAIS, June)

- [ ] Demo script storyboard.
- [ ] Pitch deck (≤ 8 slides + architecture diagram).
- [ ] Demo video (3–5 min portable recording).
- [ ] dbdemos packaging — Gold-tier requirements per design doc § 5.
- [ ] CI in `databricks-industry-solutions` repo.
- [ ] FEIP ticket, DRD, PR to dbdemos-notebooks.

---

## Open questions (carried)

- [ ] **UNSPSC taxonomy** — real UNSPSC 25.0 or synthetic 30-category mapping? (Decision will lock how the ML model's predictions are encoded in `fact_spend.unspsc_family_code`.)
- [ ] **Lakebase app placement** — standalone or embedded.
- [ ] **"Databricks on Databricks" angle** — retain from old script or drop.
- [ ] **ML SME** — design doc named TBD. Without one, Phase 2 ML model is "best effort" rather than headline.
- [ ] **FEIP timing** — Sprint 0 or Sprint 1.
- [ ] **Reference-filing privacy** — keep scrubbed or document privately.
- [ ] **Schedule for `generate_data`** — one-time or monthly re-randomization.

---

## Verification checklist (run after build_lakehouse first lands)

1. [x] `_meta.dim_period_anchors` has rows for FY2023, FY2024, Q1'25 → Q3'25.
2. [ ] `gold.fact_spend` populated with ~750k PO-line rows; `gold.fact_revenue` populated with billing events.
3. [ ] `gold.fact_fpa_actuals` totals reconcile to anchor `revenue` / `cogs + sga + rd` per (fy, fq, segment) within ±2%.
4. [x] Reconciliation gate (`99_reconcile.py`) passes for raw files.
5. [ ] Anonymization audit: zero hits for source filer name / original segment names in UC table content.
6. [ ] 10-Q replay smoke test.
