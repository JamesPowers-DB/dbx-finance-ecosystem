# ML spend classification (headline of the demo)

> Goal: an MLflow-tracked model that classifies an **invoice line** into one of 30 leaf spend categories (rolled up to 8 parents) from its description + supplier + amount + GL coordinates — so sourcing can segment strategy (consolidate suppliers in high-spend categories, flag maverick spend, focus negotiations).
>
> Training label: `gold.fact_invoices.true_category_secondary` (leaf) + `true_category_primary` (parent). Inference writes to `ml.invoice_classifications`; `gold.fact_invoices` LEFT-joins predictions through `silver.invoice_classification`.

Related: [2-tier hierarchy update (2026-05-17)](../updates/20260517_2tier_category_hierarchy.md).

## Status
- ✅ `gold.fact_invoices` populated — **312,188 rows**, FY23–FY26 Q1.
- ✅ `ml.invoice_classifications` fully populated — all 312,188 lines classified (both tiers).

## Step 1 — Feature engineering ✅ DONE
- [x] `ml/spend_classification/prepare_features.py` — pulls from `gold.fact_invoices` ⨝ `dim_supplier`; 80/20 stratified split + maverick slice. Writes `ml.spend_clf_train`, `ml.spend_clf_holdout`, `ml.spend_clf_maverick_holdout`. 15-column feature set.

## Step 2 — Baseline model ✅ DONE
- [x] `train_baseline.py` — TF-IDF (1-2 gram, 20K, sublinear_tf) + OneHotEncoder(min_frequency=50) + LightGBM (300 trees, depth 8, num_leaves 63, class_weight=balanced). Wrapped in `SpendClassifierWithTaxonomy` pyfunc emitting all four 2-tier columns (leaf→parent map baked into the artifact). Registered to `<catalog>.ml.spend_classifier@challenger`.

## Step 3 — Foundation-model variant (optional showcase)
- [ ] `train_embedding.py` — FMAPI (`databricks-bge-large-en`) embed `line_description` + small head on embedding + tabular. Compare as `@challenger_embedding`. **STILL A STUB.**

## Step 4 — Evaluation ✅ DONE
- [x] `evaluate.py` — scores present aliases on holdout + maverick_holdout + GL-account baseline floor. Reports `secondary_top1_accuracy` (leaf) + `primary_top1_accuracy` (parent). Appends to `ml.spend_clf_eval_runs`. Promotes winner to `@production` (highest maverick-slice leaf accuracy). Prints per-leaf/per-parent classification report.

## Step 5 — Batch inference ✅ DONE
- [x] `batch_inference.py` — loads `@production`, scores via `spark_udf` (struct result type), MERGEs four columns into `ml.invoice_classifications` keyed by `invoice_line_id`. Wired into `jobs/train_spend_classifier.yml` downstream of `evaluate`.

## Step 6 — Model serving (optional)
- [ ] UC-registered-model-backed serving endpoint for real-time classification (e.g. inline category suggestions in a supplier-master app).

## Step 7 — Sourcing-strategy outputs
- [ ] `gold.vw_sourcing_strategy` — joins `fact_invoices` (classified) with `dim_supplier`, `addressability='Addressable'`: category × segment × supplier-share, top maverick offenders per category, off-contract category spend. One Lakeview tile / Genie space on top.

## Open ML questions
- [ ] **UNSPSC mapping** — real UNSPSC codes vs internal 30-category code? Simplest: 1:1 map each of 30 → a chosen UNSPSC family code.
- [ ] **Model framework** — LightGBM (interpretable) vs FMAPI-embeddings NN (showcase). Could do both.
- [ ] **Confidence threshold** for "managed" classification: probably 0.75+.
