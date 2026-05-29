# Phase 1 — Consumption surfaces

> Dashboards + Genie + metric layer. Not blocked on ML; can interleave.

**See [metric_views.md](metric_views.md) — the metric layer is the current priority and the foundation for everything below.**

- [ ] Genie space configuration as a DAB resource (currently provisioned manually — see [provisioning update](../updates/20260520_lakebase_genie_provisioning.md)).
- [ ] Metric views: managed_spend, tail_spend, category_coverage, PO_compliance, on_time_payment — **tracked in [metric_views.md](metric_views.md)**.
- [ ] UNSPSC taxonomy dim — depends on the ML open question (real UNSPSC vs internal codes).
- [ ] Port AI_FORECAST + AI_QUERY queries.
- [ ] Port FinOps + Executive dashboards (AI/BI Lakeview, built on the metric views).
- [ ] New dashboard: Managed Spend Visibility.
