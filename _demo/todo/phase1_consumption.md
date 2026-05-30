# Phase 1 — Consumption surfaces

> Dashboards + Genie + metric layer. Not blocked on ML; can interleave.

**See [metric_views.md](metric_views.md) — the metric layer is the current priority and the foundation for everything below.**

- [ ] **Tear down + recreate the Genie space** (`01f154f176351736be32d20533d9f257`) from scratch — mimic the config of a separate, known-good Genie space as the baseline (instructions, sample questions, curated SQL, table set). Repoint at the metric views (`gold.mv_spend`, `gold.mv_supplier_performance`) and de-brand the display name → "Strategic Spend Analytics". Update `GENIE_SPACE_ID` in `app.yaml` / `config.py` if the id changes.
- [ ] Genie space configuration as a DAB resource (currently provisioned manually — see [provisioning update](../updates/20260520_lakebase_genie_provisioning.md)).
- [ ] Metric views: managed_spend, tail_spend, category_coverage, PO_compliance, on_time_payment — **tracked in [metric_views.md](metric_views.md)**.
- [ ] UNSPSC taxonomy dim — depends on the ML open question (real UNSPSC vs internal codes).
- [ ] Port AI_FORECAST + AI_QUERY queries.
- [ ] Port FinOps + Executive dashboards (AI/BI Lakeview, built on the metric views).
- [ ] New dashboard: Managed Spend Visibility.
