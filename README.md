# Strategic Spend Analytics

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

---

## Install — two commands

The whole demo installs with a `bundle deploy` plus one orchestrator job. The only
environment-specific input is a **SQL warehouse id** (used by the app + dashboard);
everything else is automated.

```bash
# 1) Deploy the assets (catalog, schemas, pipeline, jobs, app, dashboard).
databricks bundle deploy -t dev --var warehouse_id=<your_warehouse_id>

# 2) Build + wire everything (one job, runs the full chain).
databricks bundle run setup -t dev
```

> Find a warehouse id: `databricks warehouses list -o json | jq -r '.[] | "\(.id)\t\(.name)"'`
> (any serverless SQL warehouse works).

That's it. `setup` runs this chain (each step is also a standalone job you can re-run):

| Step | Job | What it does |
|------|-----|--------------|
| 1 | `generate_data` | Synthesize source-shaped raw files (Ariba/Fusion/CMS/Workday) + reconcile to anchors (±2%) |
| 2 | `build_lakehouse` | Run the Lakeflow pipeline (bronze → silver → gold) + validate gold vs. anchors |
| 3 | `apply_metric_views` | Create the 5 governed metric views |
| 4 | `provision_genie` | Create/refresh the Genie space **idempotently by title** (metric-view-only) |
| 5 | `grant_app_sp` | Grant the app's service principal UC schema access + Genie `CAN_RUN` |

First run is heavy (full data regen + pipeline) — budget ~15–30 min. Re-running `setup`
is safe; or run any single job, e.g. `databricks bundle run apply_metric_views -t dev`.

### Why it's this easy (design notes)
- **No service-principal wiring.** The app's SP is created by the platform at deploy;
  `grant_app_sp` resolves it automatically (`databricks apps get`) — no `<APP_SP_PRINCIPAL>`
  to hand-edit.
- **No Genie id to copy.** `provision_genie` keys the space by **title**; the app resolves
  the id by that title at runtime (`GENIE_SPACE_TITLE`). Re-running keeps the same space.
- **No hardcoded catalog.** Catalog/schema are bundle variables, substituted per target.

---

## Prerequisites
- A Databricks workspace with **serverless** SQL + jobs, and Unity Catalog.
- **Databricks CLI ≥ 0.281** authenticated (`databricks auth login` / a profile).
- Permission to create a catalog + schemas (or rights on an existing catalog — override
  with `--var catalog=<name>`), and to create a Genie space + Databricks App.
- The bundle's default profile is `DEFAULT`; both `dev` and `prod` targets currently point
  at `e2-demo-field-eng`, differentiated by catalog (`horizontal_finance_dev` vs `horizontal_finance`).

---

## What gets created

| Resource | Bundle key | Name |
|----------|-----------|------|
| Catalog + 8 schemas + raw volume | `catalog.yml` | `${var.catalog}` (`horizontal_finance_dev` in dev) |
| Lakeflow pipeline | `lakehouse` | `finance-demo-lakehouse-<target>` |
| Jobs | `generate_data`, `build_lakehouse`, `apply_metric_views`, `train_spend_classifier`, `provision_genie`, `grant_app_sp`, `setup` | `finance-demo-*-<target>` |
| Metric views | (in `apply_metric_views`) | `gold.mv_spend`, `mv_supplier_performance`, `mv_contracts`, `mv_purchase_orders`, `mv_cost_savings` |
| Genie space | `provision_genie` | `Strategic Spend Analytics (<target>)` |
| Databricks App | `spend_analytics` | `spend-analytics-<target>` |
| AI/BI dashboard | `spend_visibility` | `Strategic Spend Analytics — Spend Visibility (<target>)` |

**Catalog schemas:** `raw_data` (managed volume `files`), `bronze_ariba`, `bronze_fusion`,
`bronze_cms`, `bronze_workday`, `silver`, `gold`, `_meta` (period anchors), `ml`.

---

## Verify
```sql
-- Headline KPIs (trailing 12 months) — should be ~$2.96B total, ~50.6% managed.
SELECT ROUND(MEASURE(total_spend)/1e9, 2)        AS total_spend_b,
       ROUND(MEASURE(managed_spend_pct)*100, 1)  AS managed_pct
FROM   horizontal_finance_dev.gold.mv_spend
WHERE  invoice_date >= date_sub(current_date(), 365);
```
- **App:** `databricks apps get spend-analytics-dev -o json | jq -r .url`
- **Genie:** open *Strategic Spend Analytics (dev)* and ask *"Who are my top 5 vendors?"*
- **Dashboard:** open *Strategic Spend Analytics — Spend Visibility* in the workspace.

---

## Configuration

Bundle variables (`databricks.yml`), overridable with `--var name=value`:

| Variable | Default | Notes |
|----------|---------|-------|
| `catalog` | `horizontal_finance` (`_dev` in the dev target) | Unity Catalog for all data |
| `warehouse_id` | `""` | **Required at deploy** — app + dashboard binding |
| `schema_gold` / `schema_silver` / `schema_ml` / … | `gold` / `silver` / `ml` / … | Schema names |

App runtime config lives in `apps/spend-analytics/app.yaml`. The Genie space is resolved
by `GENIE_SPACE_TITLE` (defaults to `Strategic Spend Analytics (dev)`; set to `(prod)` for a
prod app). Set `GENIE_SPACE_ID` to pin a specific space instead.

> **Lakebase note:** the chatbot's conversation history and the manual savings ledger
> persist in Lakebase Postgres. That instance is **not** created by this bundle and is
> currently un-provisioned — those two features are inert until a Lakebase project is
> (re)provisioned and `LAKEBASE_*` set in `app.yaml`. Everything else (analytics,
> contracts, suppliers, dashboard, Genie) is UC/warehouse-backed and unaffected.

---

## Advanced / individual commands
```bash
# Run a single step instead of the whole setup chain:
databricks bundle run build_lakehouse   -t dev
databricks bundle run apply_metric_views -t dev
databricks bundle run provision_genie    -t dev
databricks bundle run grant_app_sp       -t dev
databricks bundle run train_spend_classifier -t dev   # optional ML

# Ad-hoc, outside the bundle (same logic as the jobs):
python genie/provision_genie_space.py --target dev --warehouse-id <wh>   # local Genie CLI
python scripts/grant_app_sp_access.py --target dev                       # local grant CLI
python scripts/validate_genie_sp_access.py --host <host> --genie-space-id <id> ...
```

### When a new reference 10-Q drops
The demo absorbs new quarters automatically (full workflow in
[`data/generators/README.md`](data/generators/README.md#future-10-q-ingestion-workflow)):
```bash
# Drop the 10-Q HTML into the raw volume, then:
databricks bundle run build_lakehouse -t dev
```

---

## Teardown
```bash
databricks bundle destroy -t dev          # removes catalog/schemas, pipeline, jobs, app, dashboard
# The Genie space is provisioned outside the bundle — delete it from the Genie UI,
# or: databricks api delete /api/2.0/genie/spaces/<id>
```

---

## Repository layout
```
dbx-finance-ecosystem/
├── databricks.yml              bundle root + variables + targets (dev, prod)
├── resources/                  catalog.yml, pipeline.yml (lakehouse), apps.yml, dashboards.yml
├── jobs/                       generate_data, build_lakehouse, apply_metric_views,
│                               train_spend_classifier, provision_genie, grant_app_sp, setup
├── pipelines/                  bronze / silver / gold SQL (one file per source / entity / fact)
├── data/generators/            anchor-driven synthetic source-file generators
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
The MFG industry-prod deployment plan is in
[`_demo/todo/mfg_prod_deployment.md`](_demo/todo/mfg_prod_deployment.md).
