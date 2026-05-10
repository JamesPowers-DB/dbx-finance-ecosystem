# dbx-finance-ecosystem

Helios Industrial Group — a Honeywell-anchored, fully anonymized finance data ecosystem demo. Wave 1 horizontal GTM (F-1 Spend Visibility & Strategic Sourcing Intelligence). Target: dbdemos Gold-tier.

The authoritative design lives in `_demo/00_design_context.md`. Read that first.

## Layout

```
dbx-finance-ecosystem/
├── databricks.yml                bundle root + variables + targets (dev, prod)
├── resources/
│   ├── catalog.yml               catalog finance_demo + 8 schemas + raw_files volume
│   └── pipeline.yml              one Lakeflow pipeline: bronze → silver → gold
├── jobs/
│   ├── generate_data.yml         synth raw files (Ariba/Fusion/CMS) + reconcile gate
│   ├── build_lakehouse.yml       run the pipeline + validate gold-vs-anchors
│   └── ingest_10q.yml            new 10-Q HTML → AI extract → human review → regen quarter
├── pipelines/
│   ├── bronze/                   one SQL file per source system (Ariba/Fusion/CMS)
│   ├── silver/                   one SQL file per canonical conformed entity
│   └── gold/                     one SQL file per fact / dim
├── data/generators/              data generator notebooks (referenced by generate_data job)
├── ml/notebooks/                 anchor extract/review/regen notebooks (referenced by ingest_10q job)
├── sql/                          metric views, Genie assets (Phase 2)
├── dashboards/                   Lakeview dashboards (Phase 2)
├── apps/                         Databricks Apps (Phase 2 — Lakebase Supplier Master)
├── docs/                         architecture, demo script, glossary
└── _demo/                        design context (start here)
```

## Catalog

`finance_demo` (default; override via `--var catalog=...`):

| Schema           | Purpose |
|------------------|---------|
| `raw_data`       | Managed volume `files` — landing zone for all source-system files + 10-Q HTML |
| `bronze_ariba`   | SAP Ariba shape (LFA1_*, EKKO_*, EKPO_*, RBKP_*, ARIBA_*) |
| `bronze_fusion`  | Oracle Fusion shape (gl_*, ap_*, ar_*, xla_*) |
| `bronze_cms`     | In-house CMS shape (contract, contract_line_item, ...) |
| `silver`         | Conformed canonical entities (supplier, customer, invoice, contract, ...) |
| `gold`           | Facts + dims with Phase 2 hooks reserved |
| `_meta`          | `dim_period_anchors` and `dim_period_anchors_draft` |
| `ml`             | Phase 2 ML features and registered models |

## Deploy

```bash
databricks bundle validate -t dev
databricks bundle deploy -t dev

# First-time setup
databricks bundle run generate_data -t dev
databricks bundle run build_lakehouse -t dev

# When a new 10-Q drops
# 1) Upload HTML to /Volumes/finance_demo/raw_data/files/filings/raw/10q_<period>.html
# 2) Then:
databricks bundle run ingest_10q -t dev \
  --params filing_path=/Volumes/finance_demo/raw_data/files/filings/raw/10q_2026q1.html,fiscal_year=2026,fiscal_quarter=1
databricks bundle run build_lakehouse -t dev
```

Targets: `dev` (profile `aws-e2-demo-field-eng`, mode development, default) and `prod` (host `e2-demo-west`, mode production).

## Status

Foundation scaffold only. All bronze/silver/gold SQL and generator/ml notebooks are stubs with TODO comments. Implementation of generator logic + transformation SQL is the next step (apply `fe-databricks-tools:databricks-data-generation` and `fe-databricks-tools:databricks-resource-deployment` skills against this scaffold).

Phase 2 work (UNSPSC taxonomy, spend classification ML, supplier entity resolution, contract leakage detection, savings tracking, maverick spend detection, Lakebase supplier master app, Genie spaces, agents, dashboards) is deferred — gold schema reserves column hooks so Phase 2 is additive.
