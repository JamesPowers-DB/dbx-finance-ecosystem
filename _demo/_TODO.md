# TODO — Finance Spend Analytics Demo

> ✅ **Project complete — shipped to production (2026-06-04).** All planning items are
> done; the aspect docs were marked complete and moved to [`archive/`](archive/) for
> historical context. There are no open TODOs. This file is kept as a thin index.

---

## Final state

- **Environment:** deployed to the final production demo environment — catalog
  `manufacturing`, schema `finance_spend_analytics` (single schema, layer-prefixed
  tables), workspace `fevm-mfg-industry-prod`.
- **Lakehouse + data:** Lakeflow medallion pipeline (bronze → silver → gold), anchor-driven
  synthetic generators with a ±2% reconcile gate. A **weekly self-refresh job**
  (`finance-spend-analytics-setup`, Sat 22:00 UTC) keeps the data current: generate →
  full pipeline refresh → ML inference → incremental refresh → output validation.
- **ML classifier:** TF-IDF + LightGBM pyfunc, 2-tier taxonomy (8 parents × 30 leaves),
  registered to UC `@production`; all invoice lines classified.
- **Consumption:** governed UC Metric Views (`gold_mv_*`) shared by the app, Genie, and
  the AI/BI dashboard. The **Procurement Agent** is the app's primary entry point, with
  tool calls deep-linking into each module and an action-driven home/contract surface.
- **Repo:** mirrored to `james-powers_data/dbx-finance-spend-analytics` (private).

For current architecture and deploy steps see [`00_design_context.md`](00_design_context.md),
`data/generators/README.md`, and the root [`README.md`](../README.md).

---

## Archived planning docs (`archive/`)

Completed aspect docs, retained for historical context (each carries a COMPLETED banner):

| File | Scope |
|---|---|
| [metric_views.md](archive/metric_views.md) | Standardized metric layer |
| [phase0_foundation.md](archive/phase0_foundation.md) | DAB, pipelines, dev-experience, smoke tests |
| [ml_spend_classification.md](archive/ml_spend_classification.md) | The headline classifier |
| [phase1_consumption.md](archive/phase1_consumption.md) | Genie, metric views, dashboards |
| [phase2_detection.md](archive/phase2_detection.md) | Entity resolution, contract-leakage, savings detection |
| [phase3_apps.md](archive/phase3_apps.md) | The application — features, architecture, config |
| [phase4_packaging.md](archive/phase4_packaging.md) | Demo script, deck, packaging |
| [mfg_prod_deployment.md](archive/mfg_prod_deployment.md) | Manufacturing-catalog production deployment |
| [spend_analytics_fork_migration.md](archive/spend_analytics_fork_migration.md) | Fork / single-schema migration |
| [sourcing_fork_dataset_analysis.md](archive/sourcing_fork_dataset_analysis.md) | Dataset analysis for the fork |
| [open_questions.md](archive/open_questions.md) | Carried decisions + verification checklist |

## Work log (`updates/` — one file per session)

Historical session notes remain in [`updates/`](updates/).
