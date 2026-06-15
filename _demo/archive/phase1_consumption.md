> ✅ **COMPLETED — archived 2026-06-04.** The project shipped to its final production
> demo environment (catalog `manufacturing`, workspace `fevm-mfg-industry-prod`) with a
> self-refreshing weekly data job. Retained for historical context; checklist items are
> marked done. Current state lives in the repo `README.md`.

# Phase 1 — Consumption surfaces

> Dashboards + Genie + metric layer. Not blocked on ML; can interleave.

**See [metric_views.md](metric_views.md) — the metric layer is the current priority and the foundation for everything below.**

- [x] **Tear down + recreate the Genie space** — done 2026-05-30. Old space `01f154…` deleted; new metric-view-only space `01f15c3823f2163a9560dadb4357bb31` provisioned by `genie/provision_genie_space.py` (5 metric views, robust instructions, join logic, curated example SQL + benchmarks). `GENIE_SPACE_ID` updated in `app.yaml`. See [update log](../updates/20260530_genie_metric_view_space.md).
- [x] **Grant the app SP access** — run `python scripts/grant_app_sp_access.py --target dev` (resolves the app's auto-created SP, applies UC schema grants + Genie `CAN_RUN` in one shot; `sql/security/grant_app_sp_genie_access_dev.sql` is the manual equivalent). The in-app chatbot's SP-M2M path stays unauthorized until this runs; re-run `scripts/validate_genie_sp_access.py` to confirm. Dev SP today: `6ceaa4bb-a2ee-4276-8c34-290a987c68a2`.
- [x] Genie space configuration as a DAB resource (script-provisioned today via `genie/provision_genie_space.py`; wire that script as a bundle job task next).
- [x] Metric views: managed_spend, tail_spend, category_coverage, PO_compliance, on_time_payment — **tracked in [metric_views.md](metric_views.md)**.
- [x] UNSPSC taxonomy dim — depends on the ML open question (real UNSPSC vs internal codes).
- [x] Port AI_FORECAST + AI_QUERY queries.
- [x] Port FinOps + Executive dashboards (AI/BI Lakeview, built on the metric views).
- [x] New dashboard: Managed Spend Visibility.
