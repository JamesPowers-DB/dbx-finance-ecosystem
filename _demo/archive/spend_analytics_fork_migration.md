> ✅ **COMPLETED — archived 2026-06-04.** The project shipped to its final production
> demo environment (catalog `manufacturing`, workspace `fevm-mfg-industry-prod`) with a
> self-refreshing weekly data job. Retained for historical context; checklist items are
> marked done. Current state lives in the repo `README.md`.

# Fork Migration — Finance Spend Analytics (lean, single-schema)

**Branch:** `fork/finance-spend-analytics`
**Goal:** Fork this repo into a leaner, single-schema demo and push it (fresh, squashed history) to GitHub account **`james-powers_data`** as a new repo.

## Locked decisions
| Decision | Value |
|---|---|
| Catalog | `main` (prod default; kept as `var.catalog` for easy retarget) |
| Schema | `finance_spend_analytics` (ALL layers collapse into this one schema) |
| Code model | one bundle var `schema`; table names **layer-prefixed** `bronze_` / `silver_` / `gold_` / `ml_` / `meta_`, all lowercase (metric views are `gold_mv_*`) |
| Scope | recommended lean cut (see Drop list) |
| Bundle + repo | `dbx-horizontal-finance-spend-analytics` |
| Target | single **prod** target, host `e2-demo-west.cloud.databricks.com` |
| Repo / history | fresh squashed single commit → `james-powers_data/dbx-horizontal-finance-spend-analytics` |

## STATUS — code migration complete (branch `fork/finance-spend-analytics`)
Done: prune (24 SQL, 6 generators; `gl_code_combinations` relocated) · spine · all 24 pipeline SQL renamed+prefixed · metric views (`gold_mv_*`; fixed a hardcoded-catalog bug) · all 6 jobs (single `schema`; dropped cms/workday tasks) · generators 00/01/02/03/99/_lib · app (config single schema; `app.yaml` catalog `main` + single schema + e2-demo-west deploy placeholders; routers + `db.py` prefixed) · genie (def/job/CLI; title "Finance Spend Analytics") · ML notebooks · dashboards (yaml + `.lvdash.json` → `gold_mv_*`) · grant-SP job + prod security SQL · removed dev grant SQL + `sql/pipeline_exploration/`. Verified: zero per-layer schema refs repo-wide; backend + generators + ML compile; dashboard JSON valid.

## DEFERRED (non-blocking — do not affect `bundle validate`)
- **`03_fusion_files.py` deep trim** — still emits AR / GL-journal / customer-site files (harmless; no pipeline reads them, `99` self-skips). Trim to AP+PO+supplier-sites+`gl_code_combinations` when convenient.
- **`99_reconcile.py` check pruning** — CMS-revenue / GL-balance / AP-GL cells self-skip on missing files; remove for a clean log.
- **Docs rebrand** — top-level `README.md`, `_demo/*`, `ml/README.md` still say "Strategic Spend Analytics" / mention old per-layer widgets.
- **Ad-hoc helpers** — `scripts/grant_app_sp_access.py` `DEFAULT_WAREHOUSE_ID` + `scripts/validate_genie_sp_access.py` point at the old workspace; update when used against e2-demo-west.

## Naming transform
- Bundle vars `schema_bronze_ariba`, `schema_bronze_fusion`, `schema_silver`, `schema_gold`, `schema_meta`, `schema_ml`, `schema_raw` → **collapse to one var `schema` = `finance_spend_analytics`**.
- Every SQL ref `${schema_<layer>}.<NAME>` → `${schema}.<prefix>_<lower(NAME)>`:
  - `${schema_bronze_ariba}.EBAN_PR_LINE` → `${schema}.bronze_eban_pr_line`
  - `${schema_bronze_fusion}.gl_code_combinations` → `${schema}.bronze_gl_code_combinations`
  - `${schema_silver}.invoice_ap` → `${schema}.silver_invoice_ap`
  - `${schema_gold}.fact_invoices` → `${schema}.gold_fact_invoices`
  - `${schema_meta}.dim_period_anchors` → `${schema}.meta_dim_period_anchors`
  - `${schema_ml}.invoice_classifications` → `${schema}.ml_invoice_classifications`
- Generators (`{catalog}.{schema_x}.<name>`), `metric_views/apply_metric_views.py`, `genie/`, and the app (`settings.gold`/`.silver` + every router query) get the same prefixing.
- Volume: `/Volumes/{catalog}/{schema}/files/` (raw volume moves under the one schema).

## Keep / Drop / Trim

### DROP entirely (pillars: Revenue, HR, FP&A, Accounting-GL, Customer, Outbound contracts)
Pipelines:
- `pipelines/accounting/**` — **except** the `gl_code_combinations` MV (relocated; see Trim)
- `pipelines/fpa/**` (3)
- `pipelines/hr/**` (3)
- `pipelines/revenue/**` (4)
- `pipelines/legal/bronze/cms_contracts.sql`, `pipelines/legal/silver/contract_outbound.sql`
- `pipelines/parties/bronze/fusion_customer_sites.sql`, `pipelines/parties/silver/customer.sql`, `pipelines/parties/gold/dim_customer.sql`

Generators: `04_cms_files.py` (CMS/outbound/customer), `05_workday_workers.py` (HR).

### TRIM (keep file, remove dropped-pillar parts)
- **`pipelines/accounting/bronze/fusion_gl.sql`** → relocate to `pipelines/spend/bronze/fusion_gl_code_combinations.sql` keeping **only** the `gl_code_combinations` MV (needed by `fact_invoices` for direct/indirect + addressability). Drop `gl_periods`, `gl_je_headers`, `gl_je_lines`, `gl_trial_balance`, `gl_balances`.
- **`03_fusion_files.py`** → keep AP (`ap_invoices_all`, `ap_invoice_lines_all`), PO (`po_headers_all`, `po_lines_all`), `ap_supplier_sites_all`, `gl_code_combinations`. Drop AR, GL JE headers/lines, trial balance, balances, customer sites.
- **`99_reconcile.py`** → keep spend tie-out; drop revenue + GL-balance assertions.
- **`01_period_anchors_seed.py`** → keep table as-is (spend uses cogs/sga/rd; extra cols harmless) — trim later only if desired.
- **`_lib.py`** → drop now-unused constants (customer/HR/revenue helpers) opportunistically.
- **App** — `chatbot.py`: remove the FP&A budget tool (`get_remaining_budget`/budget-threshold). `cost_savings.py`: remove the budget-vs-paid column (drops the only `fact_fpa_budgets` read).

### KEEP (the lean core)
Spend (all 13 SQL), Parties **supplier-side** (`ariba_supplier_master`, `fusion_supplier_sites`, `silver/supplier`, `gold/dim_supplier`), Legal **inbound** (`ariba_contract_workspace`, `silver/contract_inbound`), Reference (`dim_spend_category`, `dim_segment`, `dim_date`, `dim_macro_environment`), the relocated `gl_code_combinations`, ML (full classification loop), metric views (`mv_spend`, `mv_supplier_performance`, `mv_purchase_orders`, `mv_contracts`, `mv_cost_savings`), Dashboard, Genie, App.

## Phases
1. **Branch + plan** ✅ (this doc).
2. **Prune** — delete Drop list; relocate `gl_code_combinations`.
3. **Spine** — `databricks.yml` (catalog `jp_horizontal`, single `schema` var, single target), `resources/catalog.yml` (one schema + volume), `resources/pipeline.yml` (prune library list + single-schema config).
4. **Schema/catalog rename** — apply the naming transform across all kept pipeline SQL (scripted), `metric_views/`, generators, `genie/`, jobs, app (`config.py` + `app.yaml` + every router query).
5. **Trim app + generators** — FP&A budget feature out; `03`/`99`/`_lib` trims.
6. **Validate** — `databricks bundle validate`; build app frontend; collision check (no two tables share a name in the one schema).
7. **Regen on the new workspace** — deploy → `generate_data` → pipeline `--full-refresh-all` → `apply_metric_views` → (`train_spend_classifier`) → `provision_genie`.
8. **New repo** — squash to one commit; add remote for `james-powers_data/<repo>`; push.

## New-account push (needs your action)
- Confirm the **repo name** (proposed: `finance-spend-analytics`) and **bundle name** (proposed: `finance-spend-analytics`).
- Auth: `james-powers_data` must be the active GitHub credential for the push (it's one of your two authorized accounts). Likely `gh auth switch` or a per-remote token.
- I'll squash the branch to a single "Initial commit" and push to the new remote once you confirm the repo exists / I create it.

## Collision watch (single schema)
After prefixing, every table is unique by construction (`<layer>_<name>`). Verify no kept file references a table without its `${schema_x}` prefix (relative refs) before/after the transform.
