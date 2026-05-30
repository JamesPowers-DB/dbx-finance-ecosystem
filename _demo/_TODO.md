# TODO — Finance Ecosystem Demo

> Index. Detail lives in `todo/` (by aspect) and `updates/` (one file per dated work session).
> Companion files: `00_design_context.md` (architecture), `data/generators/README.md` (data flow), root `README.md` (deploy).

---

## 🎯 Active priorities (2026-05-28)

1. **[Metric Views — standardized consumption layer](todo/metric_views.md)** — replace the hand-written, drifting metric SQL scattered across app routers with governed UC Metric Views the app + Genie + dashboards all share. **Today's priority.**
2. App polish + the other walkthrough-driven updates (TBD — being scoped).

---

## 📍 Status snapshot

**Lakehouse + data:** ✅ DAB on `mode: production` (dev catalog `horizontal_finance_dev`, prod `horizontal_finance`). Generators → bronze/silver/gold; reconciliation gate passes. `gold.fact_invoices` = 312,188 rows (FY23–FY26 Q1).

**ML classifier (headline):** ✅ end-to-end — TF-IDF + LightGBM pyfunc, 2-tier taxonomy (8 parents × 30 leaves), registered to UC `@production`, all 312,188 invoice lines classified in `ml.invoice_classifications`. See [ml_spend_classification](todo/ml_spend_classification.md).

**App (Phase 3):** ✅ live — Strategic Sourcing Portal, all 5 features rendering real data. Lakebase + Genie provisioned. Home KPIs warehouse-verified (Total Spend $2.91B, Managed 99.6%, Contract Coverage 8.9%). See [phase3_apps](todo/phase3_apps.md).

---

## Aspects (`todo/`)

| File | Scope |
|---|---|
| [metric_views.md](todo/metric_views.md) | 🎯 Standardized metric layer (current priority) |
| [phase0_foundation.md](todo/phase0_foundation.md) | DAB, pipelines, HR layer, dev-experience, smoke tests |
| [ml_spend_classification.md](todo/ml_spend_classification.md) | The headline classifier (feature prep → train → eval → inference) |
| [phase1_consumption.md](todo/phase1_consumption.md) | Genie, metric views, dashboards |
| [phase2_detection.md](todo/phase2_detection.md) | Entity resolution, contract-leakage, savings detection |
| [phase3_apps.md](todo/phase3_apps.md) | Strategic Sourcing Portal — features, architecture, config, defensibility backlog |
| [phase4_packaging.md](todo/phase4_packaging.md) | Demo script, deck, dbdemos packaging, FEIP |
| [open_questions.md](todo/open_questions.md) | Carried decisions + foundation verification checklist |

## Work log (`updates/` — one file per session)

| Date | Update |
|---|---|
| 2026-05-17 | [2-tier category hierarchy](updates/20260517_2tier_category_hierarchy.md) |
| 2026-05-20/21 | [Lakebase + Genie provisioning](updates/20260520_lakebase_genie_provisioning.md) |
| 2026-05-21 | [Chatbot + Genie hardening](updates/20260521_chatbot_genie_hardening.md) |
| 2026-05-27 AM | [Procurement tightening + metric tooltips](updates/20260527a_procurement_tightening_metric_tooltips.md) |
| 2026-05-27 PM | [Live-testing bug fixes](updates/20260527b_live_testing_bugfixes.md) |
| 2026-05-27 late | [Chatbot UX polish](updates/20260527c_chatbot_ux_polish.md) |
| 2026-05-28 | [App review, TODO restructure, metric layer](updates/20260528_metric_views.md) |
| 2026-05-28 | [Procurement document lineage (contracts/events → invoices)](updates/20260528_procurement_lineage.md) |
| 2026-05-29 | [App + Genie adopt metric views; Spend Analytics dashboard; bug cleanups](updates/20260529_app_metric_view_adoption.md) |
| 2026-05-29 | [De-brand → Strategic Spend Analytics (outcome-centered, Databricks-first)](updates/20260529_debrand_spend_analytics.md) |

> **Adding an update:** create `updates/YYYYMMDD_{feature}.md` (one file per session/feature), then add a row above. Keep `_TODO.md` thin — move durable detail into the relevant `todo/` aspect file and link it.
