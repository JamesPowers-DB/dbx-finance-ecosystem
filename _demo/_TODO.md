# TODO — Helios Finance Ecosystem Demo

> Tracks the work to complete the demo end-to-end. Pivoted: the ML spend-classification model is now the headline capability. Consumption surfaces (dashboards, Genie) are deferred behind it.
>
> Companion files: `00_design_context.md` (architecture), `data/generators/README.md` (data flow), `README.md` (deploy commands).

---

## 📍 Status snapshot (as of 2026-05-20)

**Working end-to-end:**
- ✅ DAB scaffold + direct deployment engine on `mode: production` (both dev + prod) with `${bundle.target}` suffix on job/pipeline names
- ✅ Dev catalog `horizontal_finance_dev`, prod catalog `horizontal_finance`
- ✅ Generators run as serverless notebook tasks; raw files for FY23, FY24, Q1-Q3 2025
- ✅ Reconciliation gate (`99_reconcile.py`) passes ±2% / strict GL balance (5 checks: invoice spend, CMS revenue, GL balance, PR→PO→Invoice cone, AP balance)
- ✅ **Spend data model redesigned** to PR (Ariba) → PO (Fusion) → Invoice (Fusion) chain. Invoice-line grain. AP creation + payment JEs so AP balance drains. Supplier-level payment terms (Net15/30/45/60). Regulated-supplier flag drives Addressable / Non-Addressable.
- ✅ Lakeflow pipeline rewired around new model: 3 new gold facts (`fact_purchase_requests`, `fact_purchase_orders`, `fact_invoices`) replacing `fact_spend`. Silver gains `purchase_request` + `invoice_classification`.
- ✅ ML inference table pattern wired: `ml.invoice_classifications` initialized empty by data-gen seed; `silver.invoice_classification` reads it; `gold.fact_invoices` LEFT-joins → predictions are NULL until batch inference runs.
- ✅ ML notebooks re-pointed to `gold.fact_invoices` (prepare_features, batch_inference, train_baseline, evaluate, sourcing_strategy_view).

**Spend classifier (ML core) is now end-to-end:**
- ✅ `prepare_features.py` writes 3 training tables from `gold.fact_invoices`
- ✅ `train_baseline.py` trains TF-IDF + LightGBM, wraps in a taxonomy-aware pyfunc, registers to UC at `<catalog>.ml.spend_classifier@challenger`
- ✅ `evaluate.py` compares aliases + GL baseline on both holdouts at both taxonomy tiers; appends to `spend_clf_eval_runs`; promotes winner to `@production`
- ✅ `batch_inference.py` scores `fact_invoices` via `spark_udf` and MERGEs into `ml.invoice_classifications`
- ✅ 8% intra-parent label recording noise on invoice lines (`_lib.LABEL_NOISE_RATE`) — caps leaf accuracy ~92%, leaves parent accuracy near 100%. Applied only at invoice-stamp time in `03_fusion_files.py` (PRs/POs stay clean).
- ✅ **`gold.fact_invoices` confirmed populated** — 312,188 rows, FY23–FY26 Q1
- ✅ **`ml.invoice_classifications` fully populated** — all 312,188 invoice lines classified with `predicted_primary_category` + `predicted_secondary_category`

**Phase 3 (Apps) is now live and all pages verified with real data:**
- ✅ `pipelines/spend/gold/fact_cost_savings.sql` — gold table created; 1,899 rows, $47.6M savings across 30 categories
- ✅ `resources/pipeline.yml` updated to include `fact_cost_savings.sql`
- ✅ `databricks.yml` updated: `warehouse_id` variable + `sync.include` for frontend dist
- ✅ `resources/apps.yml` — new bundle resource, `helios-sourcing-portal-${bundle.target}`, warehouse OBO binding
- ✅ `apps/helios-sourcing-portal/` — full FastAPI + Vite/React/TS app scaffold (50+ files)
- ✅ App live at `https://helios-sourcing-portal-dev-1444828305810485.aws.databricksapps.com`
- ✅ All 5 features rendering with real data: Contract Burn-Down (423 active), Supplier Performance (3,000 suppliers), Cost Savings ($47.6M), Procurement Chatbot, Spend Labeling Monitor (100% coverage)
- ✅ Lakebase `helios-sourcing` provisioned; `postgres` scope added to app; Lakebase DDL runs on first user request
- ✅ OBO auth; SP env-var conflicts resolved (`DATABRICKS_CLIENT_ID`/`SECRET` cleared at startup in `main.py`)

**Latest session (2026-05-21) — Chatbot hardening + Genie SQL/feedback:**
- **Chatbot `TypeError: network error` fixed** — Root cause: SP M2M OIDC token fetch (`_get_sp_token`) raised `HTTPError 401`, which escaped the async generator and aborted the SSE stream mid-response. Fix: `_get_sp_token` now returns `None` on any error (never raises); `_stream_response` and `ask_genie` fall back to caller OBO token (`serving.serving-endpoints` + `dashboards.genie` scopes). App recreated with fresh SP (`56556626-a002-403d-b03e-925d38b8d763`) — old SP had broken client_credentials grant.
- **`node_modules` excluded from bundle sync** — Added `sync.exclude` for `apps/*/frontend/node_modules/**`, `.venv`, `__pycache__` in `databricks.yml`. App was exceeding 2000-file deployment limit (2821 files including node_modules). Now 77 files.
- **SP UC + Genie permissions** — New app SP granted: `USE_CATALOG` + `USE_SCHEMA` (gold, silver) + `SELECT` on 11 tables in `horizontal_finance_dev`; `CAN_EDIT` on Genie Space `01f154f176351736be32d20533d9f257`.
- **Tool card collapsible args** — Chatbot tool cards now collapsed by default; `chev_r`/`chev_d` toggle reveals args JSON. `expandedTools` state resets per message.
- **Genie SQL display + thumbs feedback** — `run_genie_query` now returns `conv_id`, `msg_id`, `space_id` alongside `sql` + `row_count`. Frontend parses `tool_result` SSE events for `ask_genie` and renders SQL block + 👍/👎 buttons inside expanded tool card. Thumbs call `POST /api/chat/genie-feedback` → `PUT /api/2.0/genie/…/feedback` (OBO token). Rating highlighted in lava on selection; "Feedback sent" confirmation shown.

**Deploy commands (direct CLI — bundle update mask bug workaround):**
```bash
cd apps/helios-sourcing-portal/frontend && npm run build
cd ../../..
databricks bundle deploy --target dev --profile e2-demo-field-eng --var warehouse_id=e9b34f7a2e4b0561
databricks apps deploy helios-sourcing-portal-dev \
  --source-code-path "/Workspace/Users/michael.goo@databricks.com/.bundle/dbx-finance-ecosystem/dev/files/apps/helios-sourcing-portal" \
  --profile e2-demo-field-eng
```
> Note: `bundle deploy` will error on catalog/pipeline/volume "already exists" — these are harmless. The app resource update also errors with "Invalid update mask" — ignore it; the file upload still succeeds. The `apps deploy` step is the actual redeploy.

**Bugs fixed + features added in this session:**
- SQL `MISSING_GROUP_BY` in KPI `contract_coverage_pct` query
- `DECIMAL` columns from DBSQL serialized as strings → `.toFixed()` crash on Suppliers + Labeling Monitor pages (fixed with `Number()` coercion; `fmtPct`/`fmtDelta` hardened)
- Contract type abbreviations (`SOW`, `PRICING_AGREEMENT`) didn't match actual data values (`Statement of Work`, `Framework`) — fixed in all 4 routers
- Databricks SDK `oauth + pat` conflict: `apps update` wipes resource bindings unless the full `resources` block is included — warehouse re-added; factory pattern: always pass full JSON body to `apps update`
- `Promise.all` on Cost Savings replaced with `Promise.allSettled` so reductions/summary show even if Lakebase avoidance call fails
- **Sidebar search enabled** — `searchQuery` state in `App.tsx`, real `<input>` in `Sidebar.tsx`, client-side filtering wired into Contracts (supplier name, title, region), Suppliers (name, category, region, terms), Cost Savings (supplier, category, event title), and Labeling Monitor disagreements tab. Border highlights lava on active query; `×` clear button; query clears on page navigation.
- **Genie Space + Chatbot** — Created `Helios Spend Analytics` Genie Space (`01f154f176351736be32d20533d9f257`) over 8 gold/silver procurement tables. Added `ask_genie` as a 6th tool in the FMAPI chatbot; analytics prompts now deterministically route to Genie and execute with the app service principal token (SP-only mode). `GENIE_SPACE_ID` wired into `app.yaml` + `config.py`.
- **Chatbot UX** — Centered landing layout: Databricks icon → title → **full-width input bar** → 2-column prompt tiles. Clicking a prompt populates the input (doesn't auto-send); user presses Enter or clicks Send. Bottom input bar only shows once a session is active. "+ New Chat" resets to the landing state. Auto-creates a session on first send. Session titles update from first message content.
- **Chatbot Lakebase best-effort** — All `db_conn` calls in `chatbot.py` wrapped in `try/except`; session creation returns a stub UUID without requiring Lakebase; streaming works even when Lakebase is unavailable (OBO token may lack `postgres` scope until user re-authenticates). Fall-back: single-turn mode (no history) when Lakebase is unreachable.
- **Chatbot FMAPI fix** — `serving_endpoints.query()` in SDK <=0.81 does not accept a `tools` kwarg. Replaced with a direct REST call to `POST /serving-endpoints/{name}/invocations` via `urllib` (same OBO token). Response parsed as a plain dict — no SDK version dependency. Supports full tool-call round-trips. Added `https://` guard for when Apps runtime injects `DATABRICKS_HOST` without scheme. Added `serving.serving-endpoints` to `user_api_scopes` (was getting 403 Forbidden without it).
- **Genie `ask_genie` hardening** — (1) `https://` guard on Genie host; (2) switched to **SP-only auth** for Genie API calls (no OBO fallback path); (3) deterministic routing enforces Genie calls for analytics prompts plus FMAPI missed-tool fallback; (4) structured logs now emit routing decision + auth mode + question hash for triage; (5) tool output still prioritizes Genie `text` attachment as primary `answer`.

**Next immediate steps (Phase 3 finalization):**
1. ✅ ~~Provision Lakebase instance~~ — `helios-sourcing` project live; OBO auth wired; DDL runs on first user request
2. Add DM Sans / DM Mono `.ttf` files to `apps/helios-sourcing-portal/frontend/public/ds/fonts/`, rebuild frontend, redeploy (fonts currently falling back to system fonts)
3. End-to-end chatbot test: (a) ask an analytics question — verify `ask_genie` routes to Genie; (b) submit a PR — verify it lands in `bronze_ariba.EBAN_PR_LINE`
4. Resolve bundle state drift (or accept direct CLI deploy as the workaround)
5. Move to Phase 4 — demo script, pitch deck, dbdemos packaging

---

## Phase 0 — Finish the foundation

### Pipeline SQL — DONE ✅
- [x] `pipelines/bronze/sap_ariba.sql` — 7 Auto Loader streaming tables.
- [x] `pipelines/bronze/oracle_fusion.sql` — 11 streaming tables (CSV + Parquet).
- [x] `pipelines/bronze/inhouse_cms.sql` — 6 streaming tables (line-delimited JSON).
- [x] `pipelines/silver/*.sql` — 10 conformed entities as materialized views, source-tagged.
- [x] `pipelines/gold/*.sql` — 15 facts/dims with Phase 2 hooks reserved on `fact_spend`, `dim_supplier`, `fact_revenue`.

### Build the lakehouse — DONE ✅
- [x] `bundle deploy -t dev` succeeds.
- [x] `bundle run build_lakehouse -t dev` populates bronze/silver/gold tables (after switching flat-file bronze tables from `STREAMING TABLE` to `MATERIALIZED VIEW`).

### Polish on lakehouse — optional, low priority
- [ ] Quick sanity checks in SQL editor (see `sql/pipeline_exploration/spend_overview.sql` for the full set):
  ```sql
  SELECT COUNT(*) FROM horizontal_finance_dev.gold.fact_invoices;
  SELECT segment_code, fiscal_year, fiscal_quarter, SUM(amount)/1e6 AS spend_m
    FROM horizontal_finance_dev.gold.fact_invoices
    GROUP BY ALL ORDER BY 2, 3, 1;
  -- PR → PO → invoice funnel volume
  SELECT 'PR' AS stage, COUNT(*) FROM horizontal_finance_dev.gold.fact_purchase_requests
  UNION ALL SELECT 'PO', COUNT(*) FROM horizontal_finance_dev.gold.fact_purchase_orders
  UNION ALL SELECT 'Invoice', COUNT(*) FROM horizontal_finance_dev.gold.fact_invoices;
  ```
- [ ] Implement `ml/notebooks/99_validate_gold_vs_anchors.py` (currently stub) — assert gold totals tie back to `_meta.dim_period_anchors` ±2%. Wired as final task in `build_lakehouse.yml` but currently a no-op.

### Smoke tests
- [ ] Anonymization audit: grep all UC table contents (not just code) for source filer name / original segment names.

### HR data layer — first cut DONE; future work
- [x] **`gold.dim_employees` (SCD Type 2)** sourced from `bronze_workday.workers` via `pipelines/hr/{bronze,gold}/...`. Generated by `data/generators/05_workday_workers.py`, anchor-driven (active headcount per (fy, fq, segment) tracks `_meta.dim_period_anchors.headcount_total`).
- [x] **`gold.fact_emp_quarterly_cost`** rewritten to aggregate from `dim_employees` at each anchor period's quarter-end (was: hardcoded $45k × anchor headcount).
- [ ] **Add a silver layer** for HR if/when a second HR source appears (e.g., a separate stock-comp or contractor system). Today bronze → gold is the right call with only Workday.
- [ ] **Salary raises** — generator currently doesn't model raises. Adding ~3%/quarter raise events would add SCD2 churn and let dashboards show wage-inflation trends.
- [ ] **Role-family per segment** — currently each segment can pull from any of 9 job families. Could bias (e.g., HET overweighted R&D, HAD overweighted Engineering+Operations) for realism.
- [ ] **Tie-out check** for HR — extend `99_reconcile.py` to assert that `gold.dim_employees` quarter-end active counts land within ±2% of `dim_period_anchors.headcount_total`.

### Operational / dev experience — deferred
- [ ] **Per-user dev resource naming.** Today the dev target uses `mode: production` + `${bundle.target}` suffix → resources land as e.g. `finance-demo-generate-data-dev`. Preferred convention is `[dev <user>] finance-demo-generate-data` style (matches DAB's `mode: development` auto-prefix output) so ownership is visible in the Workflows / Pipelines UI and multiple developers can deploy concurrently without name collisions on dev.
  - Why deferred: `mode: development` was the source of the state-drift corruption we just escaped. Need a stable approach that gives the `[dev <user>]` prefix without reintroducing the state-management pain.
  - Options to evaluate when we tackle this:
    1. Use `${workspace.current_user.short_name}` literally in resource `name:` fields under the dev target — same effect as the auto-preset, but deterministic and visible in YAML.
    2. Re-enable `mode: development` with a strict policy (never change naming-related config mid-cycle; always `bundle destroy` before reconfig).
    3. Per-user catalog override (e.g., `horizontal_finance_${workspace.current_user.short_name}_dev`) so dev resources are namespaced per developer at the data layer too.
  - Acceptance: two developers can `bundle deploy -t dev` from their own machines simultaneously without overwriting each other's jobs / pipelines / catalog.

- [ ] **Split the single `lakehouse` pipeline into smaller, per-subject pipelines** *(low priority — much later)*. Today everything lives under one Lakeflow pipeline (`resources/pipeline.yml` → ~35 library files spanning spend / revenue / accounting / legal / parties / fpa / hr / reference). It works and runs fast on serverless, but the monolith has downsides as the demo grows:
    - Failure in any one subject breaks the whole pipeline run.
    - Can't refresh one subject (e.g., HR) without recomputing everything.
    - Hard to attribute compute spend per subject.
    - One developer iterating on legal SQL contends with another iterating on spend SQL.

    When we tackle this: probably 4–6 pipelines (e.g., `spend_pipeline`, `revenue_pipeline`, `accounting_pipeline`, `parties_pipeline`, `legal_pipeline`, `fpa_hr_reference_pipeline`) each owning their subject's bronze/silver/gold. Cross-pipeline dependencies (e.g., `parties.dim_supplier` consumed by `spend.fact_spend`) are resolved by `expectations` or by orchestrating them via a Job DAG instead of intra-pipeline edges. Tradeoff: more pipeline resources to manage, longer total wall-clock if run serially.

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

> Goal: build an MLflow-tracked model that classifies an **invoice line** into one of 30 spend categories from its description + supplier + amount + GL coordinates — so sourcing organizations can segment their sourcing strategies (consolidate suppliers in high-spend categories, flag maverick spend, focus negotiations).
>
> Training data: `gold.fact_invoices.true_spend_category` is the supervised label; features include `line_description`, `supplier_*`, `amount`/`quantity`/`unit_price`, `gl_account`, `direct_indirect`, `addressability`. Inference writes to `ml.invoice_classifications`; `gold.fact_invoices` LEFT-joins predictions through `silver.invoice_classification`.

### Step 1 — Feature engineering  ✅ DONE
- [x] `ml/spend_classification/prepare_features.py` — pulls features from `gold.fact_invoices` joined with `dim_supplier`, splits train/holdout (80/20 stratified by leaf category, plus a separate **maverick slice** where `supplier_maverick_propensity > 0.15`). Writes:
  - `<catalog>.ml.spend_clf_train`              — features + 2-tier labels
  - `<catalog>.ml.spend_clf_holdout`            — holdout
  - `<catalog>.ml.spend_clf_maverick_holdout`   — hard-case eval slice
- [x] Feature set: 15 columns (text + 9 categorical + 4 numeric + maverick flag). See `ml/README.md` § 2 for the full table.

### Step 2 — Baseline model  ✅ DONE
- [x] `ml/spend_classification/train_baseline.py` — TF-IDF (1-2 gram, 20K features, sublinear_tf) + OneHotEncoder(min_frequency=50) + LightGBM (300 trees, depth 8, num_leaves 63, class_weight=balanced).
- [x] Wrapped in a `SpendClassifierWithTaxonomy` pyfunc that emits all four 2-tier prediction columns natively — leaf→parent map baked into the artifact at training time.
- [x] Registered to `<catalog>.ml.spend_classifier` via `mlflow.pyfunc.log_model(..., registered_model_name=...)`; alias `@challenger`.

### Step 3 — Foundation-model variant (optional, but a Databricks showcase)
- [ ] `ml/spend_classification/train_embedding.py` — uses Foundation Model API (databricks-bge-large-en) to embed `line_description`, then a small classifier head on the embedding + tabular features. Compare to baseline as `@challenger_embedding`. STILL A STUB.

### Step 4 — Evaluation  ✅ DONE
- [x] `ml/spend_classification/evaluate.py` — discovers present aliases, scores each on `holdout` + `maverick_holdout`, also scores an in-notebook `gl_account → most-common-leaf` baseline as the floor.
- [x] Reports BOTH tiers separately: `secondary_top1_accuracy` (leaf — the model's direct task) and `primary_top1_accuracy` (parent — derived inside the pyfunc).
- [x] Appends to `<catalog>.ml.spend_clf_eval_runs` for trend tracking.
- [x] Promotes the winner to `@production` (highest maverick-slice leaf accuracy, ties broken by holdout). Warns if the winner's leaf-tier margin over the GL baseline is < 10 pp.
- [x] Prints per-leaf and per-parent `sklearn.classification_report` for the winning model on the maverick slice (demo-deck material).

### Step 5 — Batch inference → ml.invoice_classifications  ✅ DONE
- [x] `ml/spend_classification/batch_inference.py` — loads `@production`, scores `gold.fact_invoices` distributed via `mlflow.pyfunc.spark_udf` with a `struct<...>` result type, MERGEs all four prediction columns into `<catalog>.ml.invoice_classifications` keyed by `invoice_line_id`.
- [x] `gold.fact_invoices` picks predictions up automatically via the LEFT JOIN through `silver.invoice_classification`. No write into the gold fact.
- [x] Wired into `jobs/train_spend_classifier.yml` as the `batch_inference` task downstream of `evaluate`. (No separate `score_spend.yml` job; the training DAG handles scheduling.)

### Step 6 — Model serving (optional)
- [ ] Create UC-registered-model-backed serving endpoint for real-time classification (e.g., used by a Lakebase Supplier Master app for inline category suggestions when manually correcting supplier records).

### Step 7 — Sourcing-strategy outputs
- [ ] `<catalog>.gold.vw_sourcing_strategy` — gold view that joins `fact_invoices` (with classified `predicted_category`) with `dim_supplier`, filtered to `addressability = 'Addressable'`, and outputs:
  - Category × segment × supplier-share table (concentration / tail-spend by category)
  - Top maverick offenders per category
  - Off-contract category spend (joined with `silver.contract_inbound`)
- [ ] One Lakeview tile or a Genie space (later) on top of this view.

### 2-tier category hierarchy — ✅ DATA + PIPELINE COMPLETE (model training open)

Implemented 2026-05-17. The supervised label is now a 2-tier taxonomy: 8 parent categories × 30 leaf categories. Sourcing organizations roll up to the parent tier for executive summary ("how much do we spend on Professional Services as a whole?") and drill into the leaf for negotiation.

**Done:**
- [x] Parent taxonomy added to `_lib.SPEND_CATEGORY_HIERARCHY` (8 parents). `CHILD_TO_PARENT` / `PARENT_TO_CHILDREN` / `PARENT_CODE_TO_NAME` lookups derived.
- [x] Materialized as `gold.dim_spend_category` via `pipelines/reference/gold/dim_spend_category.sql` (8 × 30 = 30-row VALUES clause). Wired in `resources/pipeline.yml`.
- [x] Generators (`02_ariba_files.py`, `03_fusion_files.py`) stamp `_true_category_primary` + `_true_category_secondary` on PR / PO / invoice lines. Polars schemas updated.
- [x] `99_reconcile.py` § 6 asserts every `(_true_category_primary, _true_category_secondary)` pair on raw files exists in `SPEND_CATEGORY_HIERARCHY` — fails the data-gen job on drift.
- [x] `01_period_anchors_seed.py` creates `ml.invoice_classifications` with the new 4-prediction-column schema (`predicted_primary_category`, `predicted_secondary_category`, `primary_confidence`, `secondary_confidence`). Uses `CREATE OR REPLACE` so existing tables upgrade cleanly.
- [x] Silver: `purchase_request.sql`, `purchase_order.sql`, `invoice_ap.sql`, `invoice_classification.sql` project the new columns.
- [x] Gold: `fact_purchase_requests.sql`, `fact_purchase_orders.sql`, `fact_invoices.sql` surface both true_category_* and (where applicable) all four predicted_* columns. `fact_invoices` comment calls out the demo-only nature of the truth columns.
- [x] ML: `prepare_features.py` writes `label` (leaf) + `label_primary` (parent) into the three training tables. `batch_inference.py` stub documents the join to `dim_spend_category` for primary-tier derivation. `evaluate.py` reports per-tier accuracy. `sourcing_strategy_view.py` separates parent-tier (exec) vs. leaf-tier (category manager) analytics.
- [x] Docs: `ml/README.md` rewritten for 2-tier. `sql/pipeline_exploration/spend_overview.sql` updated.

**Open (model training itself):**
- [ ] Train the baseline classifier (`train_baseline.py`). Model still emits a flat 30-leaf softmax; the parent tier is derived at inference via `dim_spend_category` lookup. A future hierarchical-softmax architecture can slot in without changing the inference table schema.
- [ ] Wire `batch_inference.py` actually MERGEing into `ml.invoice_classifications` (currently TODO stubs with implementation hints).

**Run order to land the data layer:**
1. Re-run `generate_data` job. Confirm reconcile § 6 (taxonomy parity) passes.
2. Redeploy bundle + full-refresh the lakehouse pipeline (bronze schemas have new columns).
3. Run the spend-overview exploration queries to verify both tiers populate cleanly.

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

> **Owner:** handed off to a teammate (their own Claude Code session). This section is intentionally self-contained so they can land cold and start building without back-and-forth.

**Application:** Strategic Sourcing Portal — a Databricks App for Helios' sourcing organization. Single-page web app reading from `<catalog>.gold.*` for analytics, optionally writing to Lakebase for app-specific state (saved searches, cost-savings ledger entries, chatbot history), and using the Foundation Model API (or external Claude) for the procurement chatbot.

### Onboarding (read in this order before writing any code)

1. **`_demo/00_design_context.md`** — full architecture context. Why Helios exists, how the data was synthesized, segment + geography conventions.
2. **`data/generators/_lib.py`** lines 89–325 — the 2-tier spend taxonomy (`SPEND_CATEGORIES` + `SPEND_CATEGORY_HIERARCHY`). 8 parents × 30 leaves. The portal should use parent for executive views, leaf for category-manager drill.
3. **`pipelines/spend/gold/fact_invoices.sql`** — primary data source. Read the `COMMENT` clause to understand the realistic-noise model + LEFT-JOIN inference pattern.
4. **`ml/README.md`** — the spend-classification model. Predictions land in `<catalog>.ml.invoice_classifications` and LEFT-join through `silver.invoice_classification` onto `gold.fact_invoices`. Both `predicted_primary_category` and `predicted_secondary_category` are surfaced.
5. **`sql/pipeline_exploration/spend_overview.sql`** — example queries that hit every gold table the portal will use. Run these in DBSQL first to feel the shape of the data.
6. **`databricks.yml` + `resources/*.yml`** — bundle config. The portal lands here too as `resources/apps.yml` (TBD).

### Tech stack — locked by the `dbx-app-fastapi-react` skill

**Invoke that skill first** (`Skill: dbx-app-fastapi-react`) — it scaffolds the entire stack and locks the design system. Summary of what it gives you:

- **Backend:** FastAPI + `databricks-sql-connector` for OBO (On-Behalf-Of) auth → every query runs as the logged-in user, RBAC respected.
- **Frontend:** Vite + React + TypeScript. **No Tailwind. No UI library. No chart library.** Hand-drawn SVG charts using the brand `BlobBg` / `PageHero` / `Card` / `AnimatedTileMark` primitives the skill provides.
- **Fonts:** DM Sans + DM Mono, hosted locally (skill bundles the woff2 files).
- **Auth:** OBO via the Databricks Apps user-identity header. The backend wraps every query with the user's PAT-equivalent token.
- **Deploy:** `databricks bundle deploy` provisions the app as a UC-namespaced resource. Add to `resources/apps.yml` and reference from the bundle root.

**Alternative stack:** the `dbx-app-apx` skill gives you APX (also FastAPI + React) if APX features land in time. Default to `dbx-app-fastapi-react` unless instructed otherwise.

### Bundle integration

- Put all app resources in the /apps directory
- Create `resources/apps.yml`. Name: `helios-sourcing-portal-${bundle.target}` (matches the `finance-demo-*` resource naming pattern).
- Add `app_storage` schema or use Lakebase Postgres if app needs writable state (see "Open decisions" below).
- The app needs `USE CATALOG` on `${var.catalog}` and `SELECT` on `gold.*`, `silver.*`, `ml.*`. RBAC is via OBO; do not bake service-principal credentials into the app.
- For the chatbot, the app needs `EXECUTE` on a Model Serving endpoint or `databricks-genai` Foundation Model API access.

### Data layer cheat sheet — which UC tables to use per feature

| Feature | Primary read | Joins | Writes (if any) |
|---|---|---|---|
| **Contract burn-down** | `silver.contract_inbound` (active inbound contracts, total_committed_spend, expiration_date) | `gold.fact_invoices` filtered to supplier_id in contract; aggregate amount → "% of contract consumed" | none |
| **Renewal monitoring** | `silver.contract_inbound` where `expiration_date BETWEEN today AND today + 180 days` | `silver.contract_amendment` for amendment history; `gold.fact_invoices` for trailing-12-month spend with that supplier | none (Phase 3.5 could write renewal-task entries to Lakebase) |
| **Supplier performance** | `gold.dim_supplier` (maverick_propensity, is_regulated_supplier, payment_terms, category_primary) | `gold.fact_invoices` for on-time payment %, average DPO, dispute rate; `silver.sourcing_event` + `silver.contract_inbound` for past engagement history | none |
| **Payment-terms renegotiation targeting** | `gold.dim_supplier` + `gold.fact_invoices` | Aggregate spend × current payment_terms; identify high-spend Net15/Net30 suppliers that could be pushed to Net60 for working-capital gains | none (could write target-list to Lakebase) |
| **Cost savings — Cost Reduction** | `silver.sourcing_event` (RFx events with `awarded_amount` and `pre_negotiation_baseline_amount`) | `gold.fact_invoices` to validate realized savings ("did we actually pay the lower price post-award?") | **NEEDS A NEW TABLE**: `gold.fact_cost_savings` keyed by (savings_event_id, source_type, source_id, segment_code, fiscal_quarter, savings_type='reduction'/'avoidance', amount_usd). Either materialize from a SQL view or write app-side to Lakebase. |
| **Cost savings — Cost Avoidance** | Manual entry (in-app form) referencing `silver.sourcing_event` / `silver.contract_inbound` / `gold.fact_purchase_orders` | — | Same `gold.fact_cost_savings` table; `savings_type='avoidance'`. **No automatic detection** — avoidance is "supplier asked for +20%, we negotiated to +5%" which doesn't show in actual spend; sourcing managers log it manually with attestation. |
| **Cost savings — Executive dashboard** | `gold.fact_cost_savings` | `gold.fact_fpa_budgets` / `fact_fpa_actuals` to show savings ÷ budget by segment × quarter | none |
| **Procurement chatbot** | `gold.fact_purchase_requests`, `gold.dim_supplier`, `gold.dim_spend_category`, `silver.contract_inbound`. **Tools the chatbot can call**: suggest_supplier(category, segment), get_active_contract(supplier_id), price_history(material_code), submit_pr(supplier_id, line_items, …) | Submission writes a PR. **In demo mode**: writes a synthetic row into `bronze_ariba.EBAN_PR_HEADER/LINE` directly (the lakehouse pipeline picks it up on next refresh). Real-world: would call the Ariba API. | `bronze_ariba.EBAN_*` (demo); future: external Ariba API call |
| **Spend labeling monitor** | `gold.fact_invoices` with `predicted_*_category` columns | `ml.invoice_classifications` for scored_at + model_version; `ml.spend_clf_eval_runs` for model-quality history | none |

### Domain notes for the teammate (don't skip — these drive UX decisions)

**Cost reduction vs cost avoidance:**
- **Cost reduction** = negotiated price went down. Was paying $100/unit, now paying $80/unit. Shows up in `fact_invoices.amount` going down quarter-over-quarter for the same SKU. *Captured in books.*
- **Cost avoidance** = supplier proposed a price increase, sourcing negotiated a smaller increase. Supplier wanted +20%, agreed at +5%. The 15% "avoided" never shows in actual spend (you're still paying more than before) — but it's a real value-add from sourcing. *Tracked in a separate ledger only.*
- Both belong on the executive dashboard, but they roll up differently: cost reduction reduces budget pressure (sourcing helps FP&A hit targets); cost avoidance reduces *future* budget pressure (the bigger you let avoidance grow, the more headroom for new spend without overrunning budget).
- Industry rule of thumb: avoidance is ~60–70% of total reported sourcing savings; reduction is ~30–40%. Helios numbers should land in that range for realism.

**Sourcing event lifecycle** (already in `silver.sourcing_event`):
- `RFI` (Request for Information) — early-stage; supplier discovery; no award.
- `RFP` (Request for Proposal) — competitive proposals; supplier responds with solution + price.
- `RFQ` (Request for Quote) — price-driven; spec is fixed; cheapest qualified supplier wins.
- `AUCTION` (reverse auction) — suppliers bid against each other live; price-focused; commoditized categories only.
- Award → contract → POs → invoices. Cost reduction is measured as `pre_negotiation_baseline_amount - awarded_amount`.

**Contract types** (`silver.contract_inbound.contract_type`):
- `MSA` (Master Services Agreement) — umbrella; no committed spend; defines terms.
- `SOW` (Statement of Work) — nests under MSA; committed scope + price.
- `PRICING_AGREEMENT` — schedule-of-rates; called against by POs.
- `NDA` — no spend; ignore for burn-down.
- Only `SOW` and `PRICING_AGREEMENT` have meaningful burn-down; `MSA` and `NDA` should be filtered out.

**Maverick propensity** (`dim_supplier.maverick_propensity`, 0–0.3 beta-distributed): how often this supplier sells outside its `category_primary`. High maverick_propensity = supplier who shows up across many categories = sourcing-strategy red flag (probably a generalist re-selling things, not a specialist).

**Regulated supplier** (`dim_supplier.is_regulated_supplier`, ~8%): utilities, government fees, single-source compliance. The portal should hide these from "negotiation targeting" views — they're not sourcing's to move.

### Per-feature acceptance criteria + non-goals

**1. Contract Burn-Down + Renewal Monitoring**
- ✅ Lists active contracts with: supplier, segment, contract_type, total_committed_spend, spend-to-date, % consumed, days-to-expiration.
- ✅ Visual burn-down chart per contract (hand-drawn SVG; one line per contract or stacked).
- ✅ Renewal queue: contracts expiring in the next 180 days, sorted by trailing-12-mo spend descending (the big ones first).
- ❌ Out of scope: automatic renewal-task creation in an external system. Just surface the queue; the manager kicks off externally.
- ❌ Out of scope: contract redlining / clause comparison. That's a different demo.

**2. Supplier Performance + Payment-Terms Renegotiation**
- ✅ Supplier scorecard: trailing-12-mo spend, # invoices, on-time payment %, avg DPO, current payment terms, maverick propensity, regulated flag, parent + leaf category breakdown of spend.
- ✅ "Renegotiation targets" view: top-N suppliers by spend × `(target_dpo - current_dpo)` working-capital opportunity, **filtered to `is_regulated_supplier = FALSE`**.
- ❌ Out of scope: actually pushing payment-terms changes to Ariba / Fusion. Show the recommendation; let the manager act manually.
- ❌ Out of scope: supplier risk scoring (financial health, geopolitical, etc.). Different demo.

**3. Cost Savings Tracking**
- ✅ Two write paths: auto-detected reduction (SQL view materializes from sourcing events) + manual avoidance entry (in-app form with attestation).
- ✅ Link to source: every savings entry references one of (sourcing_event_id, contract_id, po_number).
- ✅ Executive dashboard: total savings by segment × quarter, split reduction/avoidance, with budget tie-out (savings ÷ FP&A budget for that segment-quarter).
- ✅ Approval workflow: avoidance entries require a sourcing-manager attestation (logged-in user, timestamp). Reductions are auto-detected and don't need approval.
- ❌ Out of scope: integration with FP&A planning tools. Surface the impact; don't try to write back to the FP&A budget.
- ❌ Out of scope: tracking individual sourcing-manager bonuses or KPIs. Aggregate only.

**4. Procurement Chatbot**
- ✅ Natural-language intake: "I need 50 monitor mounts for the new Austin office."
- ✅ Suggests: 1–3 candidate suppliers (from `dim_supplier` filtered to category + region + non-maverick), best payment terms available, volume-discount tiers if any, applicable active contracts.
- ✅ Validation: user-confirmed PR submission (always a confirmation step before write) writes a synthetic PR to `bronze_ariba.EBAN_PR_HEADER/LINE` and returns the PR number.
- ✅ Guardrails: must reject any submission > $25,000 (sourcing-manager engagement threshold); must reject suppliers flagged regulated unless explicitly overridden.
- ❌ Out of scope: actual Ariba API integration. Demo writes to bronze directly; production would call Ariba's REST API.
- ❌ Out of scope: multi-turn negotiation. Single-shot intake → suggestions → confirm → submit.
- ❌ Out of scope: Genie / NL-to-SQL. The chatbot has explicit tools (suggest_supplier, get_active_contract, etc.); don't let it write arbitrary SQL.

**5. Spend labeling monitor (extra)**
- ✅ Coverage: % of `fact_invoices` rows with a non-null `predicted_secondary_category`, by quarter + segment.
- ✅ Confidence distribution: histograms of `secondary_confidence` and `primary_confidence`.
- ✅ "Disagreement" table: rows where `true_category_secondary <> predicted_secondary_category`. These are either model errors OR genuinely mis-coded purchases — the table is the leakage-detection surface.
- ✅ Model history: read `ml.spend_clf_eval_runs` to show champion-vs-challenger trend.
- ❌ Out of scope: retraining the model from the UI. That's a Jobs-API call the user can fire from the Workflows UI.

### Architecture decisions — locked ✅

1. **App-side state: Lakebase Postgres** — chosen for chatbot history (`chatbot_sessions`, `chatbot_messages`) and manual avoidance ledger (`savings_avoidance_entries`). Tables created on startup via DDL in `apps/helios-sourcing-portal/backend/lakebase.py`. ⚠️ Not yet provisioned — `LAKEBASE_HOST` is blank in `app.yaml`.

2. **Chatbot LLM: FMAPI, `databricks-meta-llama-3-3-70b-instruct`** — stays inside Databricks, inherits OBO auth, counts against DBUs. Endpoint name configured in `app.yaml` as `DATABRICKS_SERVING_ENDPOINT_NAME`. Tool-use implemented with 5 explicit tools (suggest_supplier, get_active_contract, price_history, check_budget_threshold, submit_pr).

3. **Cost-savings: hybrid** — `gold.fact_cost_savings` SQL MV auto-materializes reductions from awarded sourcing events; Lakebase `savings_avoidance_entries` holds manual avoidance entries with attestation. UI joins both for the executive summary.

4. **Routing: state-based React router** — `App.tsx` owns `page: PageId` state and swaps the right-pane component. No `react-router-dom` dependency.

### What's wired in the repo ✅

- All UC gold/silver tables exist and are populated (confirmed 2026-05-20).
- `pipelines/spend/gold/fact_cost_savings.sql` ✅ — created. MATERIALIZED VIEW in lakehouse pipeline.
- `resources/apps.yml` ✅ — created. Bundle resource for `helios-sourcing-portal-${bundle.target}`.
- `apps/helios-sourcing-portal/` ✅ — full app scaffold deployed. See README inside for deploy instructions.
- ML model output (`ml.invoice_classifications`) ✅ — fully populated (312,188 rows). `batch_inference.py` ran successfully.
- `silver.contract_amendment` — not implemented in pipeline (only `contract_inbound` and `contract_outbound` exist). Contracts page uses `contract_inbound` only; amendment history deferred.

### Verification checklist

1. [ ] `databricks bundle deploy -t dev` provisions the app cleanly via bundle (**blocked** — bundle state drift; `build_lakehouse` job not in state; lakehouse pipeline owned by different workspace user; workaround: direct CLI deploy used instead).
2. [x] App URL serves a React landing page using DM Sans + the brand BlobBg/PageHero/Card primitives. *(Note: font files not committed — falls back to system fonts until `.ttf` files added to `public/ds/fonts/`.)*
3. [x] OBO auth works: queries return rows scoped to the logged-in user's UC permissions.
4. [x] Every primary feature (4 + 1 extra) renders without errors against `dev` catalog data.
5. [x] Cost-savings auto-detection materializes ≥ 10 rows from existing sourcing events. *(2,500 sourcing events → cost reduction rows in `gold.fact_cost_savings`.)*
6. [ ] Chatbot submits a synthetic PR end-to-end (intake → suggestions → confirm → bronze write → PR# returned). *(Lakebase wired + Genie integrated — ready for end-to-end test.)*
7. [ ] Lakehouse pipeline refresh picks up the chatbot-submitted PR on next run.
8. [x] Hand-drawn SVG charts render; no Tailwind / no chart-library imports in `package.json`.

### Phase 3 open items

- **Fonts** ✅ — DM Sans (variable font, covers weights 100–900) + DM Mono (static Light/Regular/Italic/Medium) downloaded from Google Fonts GitHub and committed to `frontend/public/ds/fonts/`. `colors_and_type.css` updated to use two variable-font `@font-face` declarations for DM Sans instead of 6 static-weight files. DM Mono unchanged (no variable font available). Fonts are now served correctly; 404s resolved.
- **Bundle state drift** — `DATABRICKS_BUNDLE_ENGINE=direct` deploy fails on catalog/schema already-exists errors (resources owned by a different workspace user). Bundle state (`resources.json` on workspace) only has `generate_data` and `train_spend_classifier` job IDs. The `build_lakehouse` job was never created. Workaround for now: use direct CLI deploy (`databricks apps deploy`). Long-term fix: either `bundle deployment bind` the existing resources, or hand off the workspace to a single owner.

### Chatbot prompt guide

The chatbot has **6 tools** — use these prompt patterns to exercise each one:

| Prompt | Tool(s) triggered |
|---|---|
| "I need 20 laptops for the Boston office" | `suggest_supplier` → `check_budget_threshold` → `submit_pr` |
| "Find me a software licensing supplier in APAC" | `suggest_supplier` |
| "What active contracts do we have with SUP-00000042?" | `get_active_contract` |
| "What have we paid per unit for IT Hardware from that supplier?" | `price_history` |
| "I want to submit a PR for $30,000 of office furniture" | `check_budget_threshold` (will reject — over $25k threshold) |
| "What is our total spend by category this fiscal year?" | `ask_genie` (Genie NL→SQL) |
| "Which categories have the most maverick spend?" | `ask_genie` |
| "Show me our top 10 suppliers by trailing 12-month spend" | `ask_genie` |
| "Which contracts expire in the next 90 days?" | `ask_genie` |
| "How much have we saved through sourcing events this year?" | `ask_genie` |

**Guardrails built in:**
- PRs > $25,000 → auto-rejected; user must escalate to sourcing manager
- Regulated suppliers → blocked from PR submission unless user explicitly overrides
- Always asks for confirmation before `submit_pr` fires

**New Chat behavior:** clicking `+ New Chat` returns to the centered landing state (clears session context). Type a message and press Enter — a session is created automatically and the message is sent.

### App resource configuration (critical — always include full payload on `apps update`)

The app requires the scopes below and the warehouse resource binding. **Always pass the complete JSON** — `apps update` replaces (not merges) both `user_api_scopes` and `resources`:

```bash
databricks apps update helios-sourcing-portal-dev \
  --profile e2-demo-field-eng \
  --json '{
    "user_api_scopes": ["sql", "postgres", "serving.serving-endpoints", "dashboards.genie"],
    "resources": [{
      "name": "warehouse",
      "sql_warehouse": {
        "id": "e9b34f7a2e4b0561",
        "permission": "CAN_USE"
      }
    }]
  }'
```

| Scope | Used for |
|---|---|
| `sql` | All UC warehouse queries (contracts, suppliers, KPIs, labeling, cost savings) |
| `postgres` | Lakebase Postgres — chatbot session/message persistence + cost-avoidance ledger |
| `serving.serving-endpoints` | FMAPI — calling `databricks-meta-llama-3-3-70b-instruct` for chatbot responses |
| `dashboards.genie` | Preserved for user-facing Genie operations; chatbot `ask_genie` now runs with service principal token |

**If any scope is missing**: the corresponding feature fails with `PermissionDenied` at the OBO token validation step. The other features continue working. Current token in a browser session will NOT have new scopes until the user opens a new tab (re-authenticates).

**Note**: `DATABRICKS_WAREHOUSE_ID` is injected at deploy time via the `warehouse` resource binding in `app.yaml` (`valueFrom: warehouse`). It is NOT a literal value — the warehouse ID only flows through if the resource binding is present.

### Genie Space — provisioned ✅ (2026-05-21)

- **Space**: `Helios Spend Analytics` — `01f154f176351736be32d20533d9f257`
- **Tables**: `gold.fact_invoices`, `gold.dim_supplier`, `gold.fact_purchase_requests`, `gold.fact_purchase_orders`, `gold.fact_cost_savings`, `gold.dim_spend_category`, `silver.contract_inbound`, `silver.sourcing_event` (all in `horizontal_finance_dev`)
- **Warehouse**: `Serverless Starter Warehouse` (`e9b34f7a2e4b0561`)
- **Integration**: wired as the `ask_genie` tool in `apps/helios-sourcing-portal/backend/routers/chatbot.py`. `GENIE_SPACE_ID` set in `app.yaml`; `genie_space_id` in `config.py`.
- **SP-only auth**: Genie Conversation REST API now always uses the app service principal M2M token from `APP_SP_CLIENT_ID`/`APP_SP_CLIENT_SECRET`. This removes user-token scope drift from chatbot analytics responses.
- **Curate**: add instructions and certified queries in the Databricks UI to improve SQL generation quality for procurement-specific metrics.

### Service principal permission verification (dev + prod)

Use the new checker script to validate app scopes, Genie API access, and UC object access for both environments:

```bash
python scripts/validate_genie_sp_access.py \
  --profile e2-demo-field-eng \
  --host e2-demo-field-eng.cloud.databricks.com \
  --genie-space-id 01f154f176351736be32d20533d9f257 \
  --sp-client-id "$APP_SP_CLIENT_ID" \
  --sp-client-secret "$APP_SP_CLIENT_SECRET"
```

If UC probes fail, apply grants (replace `<APP_SP_PRINCIPAL>` first) by running these files in Databricks SQL editor:
- `sql/security/grant_app_sp_genie_access_dev.sql`
- `sql/security/grant_app_sp_genie_access_prod.sql`

Grant files include the full set of required objects:
- `gold.fact_invoices`
- `gold.dim_supplier`
- `gold.fact_purchase_requests`
- `gold.fact_purchase_orders`
- `gold.fact_cost_savings`
- `gold.dim_spend_category`
- `silver.contract_inbound`
- `silver.sourcing_event`

### Lakebase — provisioned ✅ (2026-05-20)

- **Project**: `projects/helios-sourcing` on `e2-demo-field-eng`
- **Endpoint**: `ep-blue-cake-d1dw80zo.database.us-west-2.cloud.databricks.com:5432`
- **Database**: `databricks_postgres`
- **Auth pattern**: per-request OBO — each connection uses the calling user's Databricks token via `w.postgres.generate_database_credential()`. DDL (`chatbot_sessions`, `chatbot_messages`, `savings_avoidance_entries`) runs lazily on the first authenticated user request.
- **Why no SP pool**: the app's service principal is not granted a Postgres role in the Lakebase instance. OBO per-request avoids this entirely and aligns with the rest of the app's auth model.
- **Config**: `LAKEBASE_HOST`, `LAKEBASE_ENDPOINT`, `LAKEBASE_DATABASE` are set in `apps/helios-sourcing-portal/app.yaml`.

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
- [x] **Lakebase app placement** — standalone project (`projects/helios-sourcing`), not embedded. OBO per-request connections; no shared pool.
- [ ] **"Databricks on Databricks" angle** — retain from old script or drop.
- [ ] **ML SME** — design doc named TBD. Without one, Phase 2 ML model is "best effort" rather than headline.
- [ ] **FEIP timing** — Sprint 0 or Sprint 1.
- [ ] **Reference-filing privacy** — keep scrubbed or document privately.
- [ ] **Schedule for `generate_data`** — one-time or monthly re-randomization.

---

## Verification checklist (run after build_lakehouse first lands)

1. [x] `_meta.dim_period_anchors` has rows for FY2023, FY2024, Q1'25 → Q3'25.
2. [x] `gold.fact_invoices` populated (312,188 rows, FY23–FY26 Q1); `gold.dim_supplier` populated (3,000 rows); `silver.contract_inbound` populated (896 active contracts).
3. [ ] `gold.fact_fpa_actuals` totals reconcile to anchor `revenue` / `cogs + sga + rd` per (fy, fq, segment) within ±2%.
4. [x] Reconciliation gate (`99_reconcile.py`) passes for raw files.
5. [ ] Anonymization audit: zero hits for source filer name / original segment names in UC table content.
7. [x] `ml.invoice_classifications` fully populated — 312,188 rows with `predicted_primary_category` + `predicted_secondary_category`; `gold.fact_invoices.predicted_secondary_category` resolves to non-NULL for all rows.
