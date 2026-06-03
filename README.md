# Finance Spend Analytics

**End-to-end spend visibility on Databricks.** Follow every dollar across the spend
lifecycle — *source / contract → request → order → invoice → paid* — and quantify
what's under management (contracted or competitively sourced) vs. leaking to the
unmanaged tail.

This is a **Databricks-first** demo: the value is the governed lakehouse, not any
single UI. Synthetic source-system data is curated by a **Lakeflow** pipeline
(bronze → silver → gold), categorized by an **MLflow** spend classifier, and exposed
through governed Unity Catalog **Metric Views** that are the single source of truth
for every consumption surface — an **AI/BI dashboard**, an **AI/BI Genie** space
("talk to your spend"), and an auxiliary **Databricks App** (FastAPI + React, OBO)
that keeps its state in **Lakebase**. All data is fully synthetic — no real entity.

> **Lean single-schema build.** Everything lives in **one schema**,
> `${var.catalog}.${var.schema}` (default schema `finance_spend_analytics`), with
> tables **layer-prefixed**: `bronze_*`, `silver_*`, `gold_*` (incl. `gold_mv_*`
> metric views), `ml_*`, `meta_*`. The bundle deploys **into an existing catalog** —
> it does not create one.

---

## Install — two commands

The whole demo installs with a `bundle deploy` plus one orchestrator job. The
environment-specific inputs are an **existing catalog** and a **SQL warehouse id**
(used by the app + dashboard); everything else is automated.

```bash
# 1) Deploy the assets (schema + volume in your catalog, pipeline, jobs, app, dashboard).
databricks bundle deploy -t prod \
  --var catalog=<existing_catalog> \
  --var warehouse_id=<your_warehouse_id>

# 2) Build + wire everything (one job, runs the full chain).
databricks bundle run setup -t prod
```

> Find a warehouse id: `databricks warehouses list -o json | jq -r '.[] | "\(.id)\t\(.name)"'`
> (any serverless SQL warehouse works). `catalog` defaults to `main` — override it to
> a catalog you already have rights on.

That's it. `setup` runs this chain (each step is also a standalone job you can re-run):

| Step | Job | What it does |
|------|-----|--------------|
| 1 | `generate_data` | Synthesize source-shaped raw files (SAP Ariba + Oracle Fusion) + reconcile spend to anchors (±2%) |
| 2 | `build_lakehouse` | Run the Lakeflow pipeline (bronze → silver → gold) + validate gold vs. anchors |
| 3 | `apply_metric_views` | Create the 5 governed metric views (`gold_mv_*`) |
| 4 | `provision_genie` | Create/refresh the Genie space **idempotently by title** (metric-view-only) |
| 5 | `grant_app_sp` | Grant the app's service principal UC schema access + Genie `CAN_RUN` |

First run is heavy (full data regen + pipeline) — budget ~15–30 min. Re-running `setup`
is safe; or run any single job, e.g. `databricks bundle run apply_metric_views -t prod`.

> **Re-generating data into streaming tables:** the bronze layer uses streaming
> tables, so overwriting source files on a later run isn't re-ingested by an
> incremental refresh. For a from-scratch data change, full-refresh the pipeline:
> `databricks bundle run lakehouse -t prod --full-refresh-all` (instead of step 2).

### Why it's this easy (design notes)
- **No service-principal wiring.** The app's SP is created by the platform at deploy;
  `grant_app_sp` resolves it automatically (`databricks apps get`) — no `<APP_SP_PRINCIPAL>`
  to hand-edit.
- **No Genie id to copy.** `provision_genie` keys the space by **title**; the app resolves
  the id by that title at runtime (`GENIE_SPACE_TITLE`). Re-running keeps the same space.
- **Catalog/schema are bundle variables**, substituted per target — point them at any
  existing catalog.

---

## Prerequisites
- A Databricks workspace with **serverless** SQL + jobs, and Unity Catalog.
- **Databricks CLI ≥ 0.281** authenticated (`databricks auth login` / a profile).
- An **existing UC catalog** you can use (the bundle does not create the catalog), with
  rights to **create a schema + managed volume** in it, plus create a Genie space + App.
  Pass it with `--var catalog=<name>` (or set the `prod` target's `catalog` variable).
- Single **`prod`** target. Set its workspace `host` (and catalog) in `databricks.yml`
  or override per deploy.

---

## What gets created

| Resource | Bundle key | Name |
|----------|-----------|------|
| Schema + raw volume (in an **existing** catalog) | `catalog.yml` | `${var.catalog}.${var.schema}` + volume `files` |
| Lakeflow pipeline | `lakehouse` | `finance-spend-analytics-lakehouse-<target>` |
| Jobs | `generate_data`, `build_lakehouse`, `apply_metric_views`, `train_spend_classifier`, `provision_genie`, `grant_app_sp`, `setup` | `finance-spend-analytics-*-<target>` |
| Metric views | (in `apply_metric_views`) | `gold_mv_spend`, `gold_mv_supplier_performance`, `gold_mv_contracts`, `gold_mv_purchase_orders`, `gold_mv_cost_savings` |
| Genie space | `provision_genie` | `Financial Spend Analytics - Strategic Sourcing` |
| Databricks App | `spend_analytics` | `spend-analytics-<target>` |
| AI/BI dashboard | `spend_visibility` | `Finance Spend Analytics — Spend Visibility` |

**Single schema:** `${var.schema}` (default `finance_spend_analytics`) holds every
layer — `bronze_*` (source-shaped raw), `silver_*` (conformed), `gold_*` (facts / dims /
`mv_*`), `ml_*` (spend classifier), `meta_*` (period anchors) — plus the managed volume `files`.

---

## Verify
```sql
-- Headline KPIs (trailing 12 months). Replace <catalog> with your catalog.
SELECT ROUND(MEASURE(total_spend)/1e9, 2)        AS total_spend_b,
       ROUND(MEASURE(managed_spend_pct)*100, 1)  AS managed_pct
FROM   <catalog>.finance_spend_analytics.gold_mv_spend
WHERE  invoice_date >= date_sub(current_date(), 365);
```
- **App:** `databricks apps get spend-analytics-prod -o json | jq -r .url`
- **Genie:** open *Financial Spend Analytics - Strategic Sourcing* and ask *"Who are my top 5 vendors?"*
- **Dashboard:** open *Finance Spend Analytics — Spend Visibility* in the workspace.

---

## Configuration

Bundle variables (`databricks.yml`), overridable with `--var name=value`:

| Variable | Default | Notes |
|----------|---------|-------|
| `catalog` | `main` (per-target var) | Existing UC catalog to deploy into — the bundle does **not** create it (point this at a catalog that already exists) |
| `schema` | `finance_spend_analytics` | **Single** schema holding every layer; tables are layer-prefixed (`bronze_` / `silver_` / `gold_` / `ml_` / `meta_`; metric views are `gold_mv_*`) |
| `raw_volume` | `files` | Managed volume (under `schema`) for source-system files |
| `warehouse_id` | `""` | **Required at deploy** — app + dashboard binding |

App runtime config lives in `apps/spend-analytics/app.yaml`. The Genie space is resolved
by `GENIE_SPACE_TITLE` (must match `genie/genie_space_def.space_title`, currently
`Financial Spend Analytics - Strategic Sourcing`). Set `GENIE_SPACE_ID` to pin a specific
space instead.

> **Lakebase note:** the chatbot's conversation history and the manual savings ledger
> persist in Lakebase Postgres. That instance is **not** created by this bundle —
> those two features are inert until a Lakebase project is provisioned and `LAKEBASE_*`
> set in `app.yaml`. Everything else (analytics, contracts, suppliers, dashboard, Genie)
> is UC/warehouse-backed and unaffected.

---

## Advanced / individual commands
```bash
# Run a single step instead of the whole setup chain:
databricks bundle run build_lakehouse        -t prod
databricks bundle run apply_metric_views     -t prod
databricks bundle run provision_genie        -t prod
databricks bundle run grant_app_sp           -t prod
databricks bundle run train_spend_classifier -t prod   # optional ML

# Full-refresh the pipeline (required after re-generating source files):
databricks bundle run lakehouse -t prod --full-refresh-all

# Ad-hoc, outside the bundle (same logic as the jobs):
python genie/provision_genie_space.py --target prod --warehouse-id <wh>   # local Genie CLI
python scripts/grant_app_sp_access.py --target prod                       # local grant CLI
```

### Adding a new fiscal period
New quarters are driven by anchor rows in `data/generators/01_period_anchors_seed.py`
(`CONSOL_PERIODS`). Add a tuple, then re-generate + full-refresh:
```bash
databricks bundle run generate_data -t prod
databricks bundle run lakehouse     -t prod --full-refresh-all
```
See [`data/generators/README.md`](data/generators/README.md) for the full workflow.

---

## Teardown
```bash
databricks bundle destroy -t prod   # removes the schema + volume, pipeline, jobs, app, dashboard
# The catalog is NOT bundle-managed (pre-existing) and is left intact.
# The Genie space is provisioned outside the bundle — delete it from the Genie UI,
# or: databricks api delete /api/2.0/genie/spaces/<id>
```

---

## Repository layout
```
dbx-horizontal-finance-spend-analytics/
├── databricks.yml              bundle root + variables + single prod target
├── resources/                  catalog.yml (schema + volume), pipeline.yml (lakehouse), apps.yml, dashboards.yml
├── jobs/                       generate_data, build_lakehouse, apply_metric_views,
│                               train_spend_classifier, provision_genie, grant_app_sp, setup
├── pipelines/                  bronze / silver / gold SQL (spend + supplier + inbound contracts + reference)
├── data/generators/            anchor-driven synthetic source-file generators (Ariba + Fusion)
├── metric_views/               apply_metric_views.py — the 5 governed metric views
├── genie/                      genie_space_def.py (shared) + provision_genie_space_job.py (job)
│                               + provision_genie_space.py (CLI)
├── scripts/                    grant_app_sp_job.py (job) + *_access.py / validate_*.py (CLI)
├── dashboards/                 spend_visibility.lvdash.json (AI/BI)
├── apps/spend-analytics/       FastAPI + React app (OBO; Lakebase state)
├── ml/                         spend-classifier + validation notebooks
└── _demo/                      design context (start with 00_design_context.md) + todo/
```

The authoritative design lives in [`_demo/00_design_context.md`](_demo/00_design_context.md).
