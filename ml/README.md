# ML — Helios Finance Ecosystem Demo

The headline ML capability of this demo is **automatic spend classification** — given a PO line item from procurement, predict which of 30 spend categories it belongs to. Sourcing organizations use these classifications to consolidate suppliers in high-spend categories, flag maverick (off-pattern) purchases, and focus negotiations where the dollars actually are.

Two ML / governance workflows live in this folder:

| Folder | Purpose | Status |
|---|---|---|
| `spend_classification/` | **Headline model** — multi-class classifier on PO line items | In progress |
| `notebooks/` | Gold-vs-anchor validator. (The 10-Q AI-ingestion notebooks live under `data/ml/` since they belong to the data-generation effort, not the demo ML effort.) | Stubs |

The rest of this doc is the spend-classification model spec.

---

## 1. The problem

Helios has ~750K purchase-order line items per multi-year window across procurement (SAP Ariba). Each PO line is a free-text description (`TXZ01`) plus structured fields — supplier, material group, segment, amount, UoM. Today there is **no consistent taxonomy**: line items are classified inconsistently across cost centers because:

- SAP's `MATGROUP` (material group) is filled in 92% of the time but ~8% of those are mislabeled.
- Category managers tag purchases manually for some categories but not others.
- Suppliers often span 2–3 related categories; maverick purchases drift further.

**Goal:** an ML model that predicts the canonical category for every PO line, surfacing structured analytics for sourcing:
- Spend concentration by category × segment × supplier
- Maverick spend (suppliers buying outside their primary category)
- Off-contract spend by category (joined with `contract_inbound`)

**Target accuracy:** ≥ 85% top-1 on holdout, **outperforming** a MATGROUP-only lookup baseline.

---

## 2. Data

### Source — `gold.fact_spend` (joined with `dim_supplier`)

One row per PO line. Built by the Lakeflow pipeline from Ariba bronze. ~750K rows across FY23, FY24, Q1–Q3 2025.

**Supervised label** — `fact_spend.true_spend_category`

| Where it comes from | Encoded by | Demo nuance |
|---|---|---|
| Generator stamps it on every PO line | One of 30 codes from `data/generators/_lib.SPEND_CATEGORIES` | Represents the manual-category-management step that exists in real Helios-style organizations. In production this label would come from a human-curated mapping table; for the demo it's deterministic ground truth. |

### Features (full inventory)

| Group | Feature | Source | Encoding |
|---|---|---|---|
| **Text** | `line_description` (TXZ01) | `fact_spend.line_description` | TF-IDF (1–2 gram) baseline; Foundation Model embedding (`databricks-bge-large-en`) for the optional variant |
| **Categorical (high cardinality)** | `supplier_id` | `fact_spend.supplier_id` | Target encoding |
| | `material_group_code` (MATGROUP) | `fact_spend.material_group_code` | One-hot. **Intentionally noisy** at the data layer — 8% mislabel rate — to force the model to combine signals. |
| **Categorical (low cardinality)** | `segment_code` | `fact_spend.segment_code` | One-hot |
| | `supplier_segment_affinity` | `fact_spend.supplier_segment_affinity` | One-hot |
| | `supplier_region` | `fact_spend.supplier_region` | One-hot |
| | `po_doc_type` (BSART) | `fact_spend.po_doc_type` | One-hot |
| | `uom` (MEINS) | `fact_spend.uom` | One-hot |
| **Numeric (log-transformed)** | `extended_amount` (NETWR) | `fact_spend.extended_amount` | `log1p()` |
| | `quantity` (MENGE) | `fact_spend.quantity` | `log1p()` |
| | `unit_price` (NETPR) | `fact_spend.unit_price` | `log1p()` |
| **Derived** | `supplier_maverick_propensity` | `dim_supplier.maverick_propensity` | Numeric 0–0.3 |
| | `category_primary_hint` | `dim_supplier.category_primary` | One-hot — supplier's primary category (75% match rate with the actual label) |

Total: **12 features** in the v1 feature set, plus optional ablation features (currency, country, fiscal year/quarter, is_cross_segment_supplier).

---

## 3. Model architecture

Two parallel models trained and compared:

### Baseline — TF-IDF + LightGBM

```
line_description ─▶ TF-IDF (1-2 gram, max_features=50000)  ──┐
supplier_id ─────▶ Target encoder ──────────────────────────┤
material_group_code, segment_code,                          ├──▶ LightGBM
supplier_segment_affinity, supplier_region,                 │   (30-class softmax,
po_doc_type, uom ─▶ One-hot                                 │    depth ≤ 8,
log_extended_amount, log_quantity, log_unit_price ─────────┤    ~500 trees)
supplier_maverick_propensity ──────────────────────────────┤
category_primary_hint ─▶ One-hot ──────────────────────────┘
```

Fast to train (~2 min on serverless), interpretable (LightGBM gives per-feature importance + per-prediction SHAP), strong baseline for tabular+text mixes.

### Variant — Foundation Model embedding + classifier

```
line_description ─▶ databricks-bge-large-en embedding (1024-dim) ─┐
[same categorical + numeric features as baseline] ─────────────────┴─▶ Simple classifier
                                                                       (logistic regression
                                                                        or small MLP on top
                                                                        of [embedding ; tabular])
```

Slower to train (embedding call latency), but probably stronger on the *rare descriptions* and *cross-category* cases — and gives a clean Databricks-product story (FMAPI inside a classification pipeline).

The two are framed as **challenger vs. champion**: register both to UC, evaluate, promote the winner.

---

## 4. Training process

Six notebooks in `ml/spend_classification/`, executed in order via a `jobs/train_spend_classifier.yml` job (TBD):

### `prepare_features.py` — feature engineering + train/holdout split

Reads `gold.fact_spend` joined with `dim_supplier`. Writes three tables to `<catalog>.ml`:

| Table | Rows | Purpose |
|---|---|---|
| `spend_clf_train` | ~600K | Stratified 80% per category. Training set. |
| `spend_clf_holdout` | ~120K | Stratified 20% per category. **Excludes** maverick-supplier POs (kept separately). Used for primary accuracy metric. |
| `spend_clf_maverick_holdout` | ~30K | Suppliers with `maverick_propensity > 0.15`. The **hard-case eval slice**. Models that pattern-match supplier→category fail here; models that read description + amount + UoM should succeed. |

Stratification by `true_spend_category` ensures every class has rows in both splits. Deterministic split (seeded).

### `train_baseline.py` — TF-IDF + LightGBM

- Build sklearn `Pipeline` with `ColumnTransformer` (TF-IDF on text, OneHotEncoder on categorical, passthrough on numeric).
- LightGBM `LGBMClassifier(objective='multiclass', num_class=30, n_estimators=500, max_depth=7, learning_rate=0.05)`.
- MLflow autolog → logged params, metrics, model, signature, input example.
- Register to `<catalog>.ml.spend_classifier` with alias `@challenger`.

### `train_embedding.py` — Foundation Model API variant (optional)

- Call `databricks-bge-large-en` via `mlflow.deployments` SDK to embed `line_description` in batches (chunks of 1000).
- Cache embeddings in `<catalog>.ml.spend_clf_embeddings_cache` (keyed by hash of description) so re-runs don't re-embed.
- Train classifier head (logistic regression or 2-layer MLP) on `[embedding ; tabular_features]`.
- MLflow autolog; register as `@challenger_embedding` for comparison.

### `evaluate.py` — three slices, side-by-side comparison

For each model alias (`@challenger`, `@challenger_embedding`, plus a `@matgroup_baseline` lookup model that predicts via `material_group_code → most_common_category`):

| Metric | Slice | Target |
|---|---|---|
| Top-1 accuracy | `spend_clf_holdout` | ≥ 85% |
| Top-3 accuracy | `spend_clf_holdout` | ≥ 95% |
| Per-class F1 | `spend_clf_holdout` | macro-avg ≥ 0.80 |
| **Maverick-slice top-1** | `spend_clf_maverick_holdout` | **≥ 70%** — the headline number for sourcing teams |
| Confidence calibration (ECE) | `spend_clf_holdout` | ≤ 0.05 |
| MATGROUP-baseline beat | `spend_clf_holdout` | model must outperform by ≥ 10 pp |

Logs a comparison table to MLflow + writes `<catalog>.ml.spend_clf_eval_runs` as a Delta table for the dashboard to consume.

Whichever model wins (by maverick-slice accuracy, then overall) gets aliased `@production` and proceeds to batch inference.

### `batch_inference.py` — score all `fact_spend` rows + write back

- Load `@production` model.
- Score every row in `<catalog>.gold.fact_spend`.
- Write predictions into the reserved Phase 2 hook columns via a MERGE:
  - `unspsc_family_code` ← predicted class
  - `classification_confidence` ← max-prob from softmax
  - `managed_spend_flag` ← `confidence > 0.75 AND supplier_canonical_id IS NOT NULL` (proxy: well-classified + supplier in canonical master)
- Idempotent — safe to re-run after retraining.

### `sourcing_strategy_view.py` — the *value* delivered to sourcing

Creates `<catalog>.gold.vw_sourcing_strategy` — a denormalized view that the eventual dashboards / Genie space consume:

- **Category concentration**: spend × supplier-share-of-category × Helmholtz Herfindahl index for monopsony risk.
- **Maverick spend per category**: total $ where `supplier.category_primary != predicted_category` (i.e., supplier shouldn't be selling this).
- **Off-contract category spend**: joined with `silver.contract_inbound` to flag spend that isn't covered by an active inbound contract.
- **Tail spend per segment**: sum of spend in categories where one segment buys < 5% of company total — candidates for consolidation.

Plus a small fact `<catalog>.ml.spend_clf_predictions` keeping every prediction for downstream model-monitoring queries.

---

## 5. File layout

```
ml/
├── README.md                              ← this file
├── notebooks/
│   └── validate_gold_vs_anchors.py       ← assert gold ties to anchors ±2%
└── spend_classification/                  ← headline ML project (in progress)
    ├── prepare_features.py
    ├── train_baseline.py                 ← TF-IDF + LightGBM
    ├── train_embedding.py                ← Foundation Model API variant (optional)
    ├── evaluate.py
    ├── batch_inference.py
    └── sourcing_strategy_view.py

# Effort-1 ML notebooks (data ingestion) live in `data/ml/`:
#   data/ml/extract_10q.py
#   data/ml/review_anchor_draft.py
#   data/ml/regenerate_quarter.py
```

---

## 6. Operational notes

### Job orchestration

A `jobs/train_spend_classifier.yml` job (TBD) chains the six spend-classification notebooks:

```
prepare_features
    │
    ├──▶ train_baseline ─────┐
    └──▶ train_embedding ────┴──▶ evaluate ──▶ batch_inference ──▶ sourcing_strategy_view
                                  (promotes
                                   winner to
                                   @production)
```

### Dependencies

Beyond the demo's existing `polars` + `mimesis`, ML training needs:

```
scikit-learn>=1.5
lightgbm>=4.5
mlflow>=2.20
databricks-sdk          # for FMAPI calls
```

Added as a new `environment_key: ml_train` in the training job's `environments` block (separate from the `default` env used by generators).

### Re-training cadence

The demo is a one-shot train. In a real deployment, retraining cadence would be:
- Weekly batch retrain when a new 10-Q drops and `data/ml/regenerate_quarter.py` adds new POs.
- Drift monitoring on the `maverick_propensity` distribution — retrain if it shifts.

### Evaluation transparency

The deliberate **8% MATGROUP noise** and **6% maverick spend** in the generator are documented design choices, not bugs. The eval metrics above account for them — a model that scores 100% on holdout would be suspicious (probably leaking the label via supplier_id alone).

---

## 7. References

- Architecture context: `_demo/00_design_context.md` (§ 4 — Phase 2 ML hooks reserved on `fact_spend`).
- ML feature signal design: `data/generators/README.md` (§ "Spend classification — what's in the data for ML").
- The 30 categories themselves: `data/generators/_lib.py` (`SPEND_CATEGORIES`).
