# 2026-05-17 — 2-tier spend-category hierarchy (data + pipeline)

> Status: **DATA + PIPELINE COMPLETE** (model training tracked in [ml_spend_classification](../todo/ml_spend_classification.md)).

The supervised label is now a 2-tier taxonomy: **8 parent categories × 30 leaf categories**. Sourcing organizations roll up to the parent tier for executive summary ("how much do we spend on Professional Services as a whole?") and drill into the leaf for negotiation.

## Done

- Parent taxonomy added to `_lib.SPEND_CATEGORY_HIERARCHY` (8 parents). `CHILD_TO_PARENT` / `PARENT_TO_CHILDREN` / `PARENT_CODE_TO_NAME` lookups derived.
- Materialized as `gold.dim_spend_category` via `pipelines/reference/gold/dim_spend_category.sql` (30-row VALUES clause). Wired in `resources/pipeline.yml`.
- Generators (`02_ariba_files.py`, `03_fusion_files.py`) stamp `_true_category_primary` + `_true_category_secondary` on PR / PO / invoice lines. Polars schemas updated.
- `99_reconcile.py` § 6 asserts every `(_true_category_primary, _true_category_secondary)` pair on raw files exists in `SPEND_CATEGORY_HIERARCHY` — fails the data-gen job on drift.
- `01_period_anchors_seed.py` creates `ml.invoice_classifications` with the 4-prediction-column schema (`predicted_primary_category`, `predicted_secondary_category`, `primary_confidence`, `secondary_confidence`). Uses `CREATE OR REPLACE` so existing tables upgrade cleanly.
- Silver: `purchase_request.sql`, `purchase_order.sql`, `invoice_ap.sql`, `invoice_classification.sql` project the new columns.
- Gold: `fact_purchase_requests.sql`, `fact_purchase_orders.sql`, `fact_invoices.sql` surface both `true_category_*` and (where applicable) all four `predicted_*` columns. `fact_invoices` comment calls out the demo-only nature of the truth columns.
- ML: `prepare_features.py` writes `label` (leaf) + `label_primary` (parent). `evaluate.py` reports per-tier accuracy. `sourcing_strategy_view.py` separates parent-tier (exec) vs. leaf-tier (category manager) analytics.
- Docs: `ml/README.md` rewritten for 2-tier. `sql/pipeline_exploration/spend_overview.sql` updated.

## Run order to land the data layer

1. Re-run `generate_data` job. Confirm reconcile § 6 (taxonomy parity) passes.
2. Redeploy bundle + full-refresh the lakehouse pipeline (bronze schemas have new columns).
3. Run the spend-overview exploration queries to verify both tiers populate cleanly.
