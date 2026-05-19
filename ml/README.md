# ML — Helios Finance Ecosystem Demo

The headline ML capability of this demo is **automatic spend classification** — given an AP invoice line, predict which of 30 leaf spend categories (rolled up to 8 parent categories) it belongs to. Sourcing organizations use these classifications to consolidate suppliers in high-spend categories, flag maverick (off-pattern) purchases, and focus negotiations where the dollars actually are. The 2-tier taxonomy lets executives roll up ("how much do we spend on Professional Services as a whole?") and lets category managers drill into the leaf for negotiation.

Two ML / governance workflows live in this folder:

| Folder | Purpose | Status |
|---|---|---|
| `spend_classification/` | **Headline model** — multi-class classifier on AP invoice line items | Feature prep, training, evaluation, and batch inference all implemented end-to-end. `train_embedding.py` (FM embedding variant) remains a stub for the ML expert. |
| `notebooks/` | Gold-vs-anchor validator. | Stub |

The rest of this doc is the spend-classification model spec.

---

## 1. The problem

Helios has hundreds of thousands of AP invoice line items per multi-year window across procurement. Each line is a free-text description plus structured fields — supplier, segment, amount, payment terms, GL account. Today there is **no consistent fine-grained taxonomy**: line items are classified inconsistently across cost centers because:

- Suppliers often span 2–3 related categories.
- Category managers tag purchases manually for some categories but not others.
- Non-PO direct vouchers (~10% of invoices) skip the procurement chain entirely, so they have no upstream PR/PO categorization.

**Goal:** an ML model that predicts a canonical category for every invoice line, surfacing structured analytics for sourcing:
- Spend concentration by category × segment × supplier
- Maverick spend (suppliers buying outside their primary category)
- Off-contract spend by category (joined with `contract_inbound`)

**Target accuracy:** ≥ 85% leaf-tier top-1 on holdout (≥ 95% parent-tier), **outperforming** a `gl_account → most-common-leaf-category` lookup baseline by ≥ 10 percentage points on the leaf tier.

### Rule-based classifications that are NOT ML

Two adjacent classifications are **deterministic rules** computed in `gold.fact_invoices`, not predicted by the model. The ML expert should know they exist so they're not confused with the model's job:

| Column | Rule | Why it's not ML |
|---|---|---|
| `direct_indirect` | `Direct` if `gl_account_type = 'COGS'`, else `Indirect` | A GL coding decision made by Finance — deterministic, not noisy |
| `addressability` | `Non-Addressable` if `dim_supplier.is_regulated_supplier = TRUE`, else `Addressable` | Regulated suppliers (utilities, government) are sourcing's "untouchable" tier — a config-driven supplier attribute |

The ML model focuses solely on predicting the spend category — the 8-parent × 30-leaf taxonomy stored in `gold.dim_spend_category`.

---

## 2. Data

### Source — `gold.fact_invoices` (joined with `dim_supplier`)

One row per AP invoice line. Built by the Lakeflow pipeline from Fusion AP (`ap_invoices_all` headers + `ap_invoice_lines_all` lines). Labeled rows where `true_category_secondary IS NOT NULL` are the training payload.

**Supervised labels (2-tier)**

| Column | What it is | Cardinality |
|---|---|---|
| `true_category_primary` | Parent code (e.g. `Professional_Services`) | 8 classes |
| `true_category_secondary` | Leaf code (e.g. `Professional_Services_Consulting`) | 30 classes |

> ⚠ **Demo-only ground truth.** These columns **wouldn't exist on real Helios AP data**. They're stamped on the synthetic dataset so the demo can train a supervised classifier against a deterministic label set. In a production engagement the customer would supply a partial manually-curated training set (typically a few thousand hand-labeled invoice lines) and the model would classify the unlabeled majority. The columns ride through `gold.fact_invoices` for demo convenience; the operational data shape would otherwise have `MATGROUP` + `gl_account` + `line_description` only.

> 🎲 **Realistic recording noise.** Invoice lines have ~8% intra-parent label noise applied at recording time (controlled by `_lib.LABEL_NOISE_RATE`). The line's content (vocabulary, `gl_account`, supplier) stays consistent with the *actual* category, but `true_category_secondary` is swapped to a sibling under the same parent ~8% of the time (Legal ↔ Audit ↔ Consulting; HVAC_Equipment ↔ Building_Controls). PR and PO lines are NOT noised — mis-tagging is modeled where it actually happens in the wild: at GL entry, not procurement intent. This caps leaf-tier accuracy at ~92% on the recorded label; parent-tier accuracy stays near 100% because the noise is intra-parent. The model is meaningfully challenged: it has to learn that `gl_account` + `line_description` sometimes disagree with the recorded label — exactly the signal sourcing organizations want surfaced as "this purchase was mis-coded".

**Taxonomy source of truth:** `gold.dim_spend_category` — materialized from `pipelines/reference/gold/dim_spend_category.sql`, mirrored from `data/generators/_lib.SPEND_CATEGORY_HIERARCHY`. The reconcile step asserts parity. The 8 parents:

`Direct_Materials_Components` (12 leaves) · `Raw_Materials` (2) · `MRO_Field_Services` (2) · `Software_Cloud` (3) · `IT_Telecom` (2) · `Professional_Services` (3) · `Facilities_GA` (5) · `Logistics` (1) = 30 leaves total.

### Features (v1 set)

| Group | Feature | Source | Encoding hint |
|---|---|---|---|
| **Text** | `line_description` | `fact_invoices.line_description` | TF-IDF (1–2 gram) baseline; Foundation Model embedding (`databricks-bge-large-en`) for the optional variant |
| **Categorical (high cardinality)** | `supplier_id` | `fact_invoices.supplier_id` | Target encoding (~3K suppliers) |
| **Categorical (low cardinality)** | `segment_code` | `fact_invoices.segment_code` | One-hot (4 segments: HAD / HPA / HSB / HET) |
| | `payment_terms` | `fact_invoices.payment_terms` | One-hot (Net15 / Net30 / Net45 / Net60) |
| | `currency` | `fact_invoices.currency` | One-hot |
| | `supplier_region` | `fact_invoices.supplier_region` | One-hot (NA / EMEA / APAC / LATAM) |
| | `gl_account` | `fact_invoices.gl_account` | One-hot. **Important signal floor** — the model has to beat a `gl_account → most-common-category` lookup. |
| | `direct_indirect` | `fact_invoices.direct_indirect` | One-hot (Direct / Indirect — derived from GL account type) |
| | `addressability` | `fact_invoices.addressability` | One-hot (Addressable / Non-Addressable — derived from supplier flag) |
| | `category_primary_hint` | `dim_supplier.category_primary` | One-hot — supplier's primary category (~75% match rate with the actual label) |
| **Numeric (log-transformed)** | `log_amount` | `fact_invoices.amount` | `log1p()` |
| | `log_quantity` | `fact_invoices.quantity` | `log1p()` |
| | `log_unit_price` | `fact_invoices.unit_price` | `log1p()` |
| **Derived** | `supplier_maverick_propensity` | `dim_supplier.maverick_propensity` | Numeric 0–0.3 |
| | `is_maverick_supplier` | `supplier_maverick_propensity > maverick_threshold` (default 0.15) | Boolean — drives the maverick eval slice |

Total: **15 features** in v1. Optional ablation features the ML expert may want to try: `supplier_country`, `fiscal_year`/`fiscal_quarter`, `po_matched_flag` (Y/N — PO-matched vs. direct voucher).

### Inference-output table — `<catalog>.ml.invoice_classifications`

`batch_inference.py` MERGEs predictions into this Delta table keyed by `invoice_line_id`. `silver.invoice_classification` reads it, and `gold.fact_invoices` LEFT-joins through that silver view → predictions appear on every invoice row, `NULL` until the model has scored.

Schema (initialized empty by `data/generators/01_period_anchors_seed.py`):

| Column | Type | Notes |
|---|---|---|
| `invoice_line_id` | BIGINT | FK → `fact_invoices.invoice_line_id` |
| `predicted_secondary_category` | STRING | argmax over the 30-leaf softmax |
| `predicted_primary_category` | STRING | Parent — derived via `dim_spend_category[leaf].primary_code` lookup at inference time |
| `secondary_confidence` | DOUBLE | Max softmax probability (leaf tier) |
| `primary_confidence` | DOUBLE | Sum of softmax probabilities over all leaves under the predicted parent (always ≥ `secondary_confidence`) |
| `model_version` | STRING | MLflow registered-model version |
| `scored_at` | TIMESTAMP | Wall-clock at inference |

**The model is still a flat 30-class softmax** — the 2-tier split happens at inference time via a `dim_spend_category` lookup, not in the model itself. This keeps the model simple and lets a future hierarchical-softmax architecture slot in without changing this schema.

**The LEFT-JOIN architecture** is intentional: it decouples model lifecycle from data lifecycle. The data pipeline can run before the model exists; predictions surface only when the inference job has run. No nullability headaches in `fact_invoices`; no MERGE-back into gold facts; clean roll-back if a model has to be unpublished (just truncate `ml.invoice_classifications`).

---

## 3. Model architecture

Two parallel models trained and compared:

### Baseline — TF-IDF + LightGBM

```
line_description ─▶ TF-IDF (1-2 gram, max_features=50000)  ──┐
supplier_id ─────▶ Target encoder ──────────────────────────┤
segment_code, payment_terms, currency,                       ├──▶ LightGBM
supplier_region, gl_account, direct_indirect,                │   (30-class softmax,
addressability, category_primary_hint ─▶ One-hot ───────────┤    depth ≤ 8,
log_amount, log_quantity, log_unit_price ───────────────────┤    ~500 trees)
supplier_maverick_propensity ───────────────────────────────┘
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

Six notebooks in `ml/spend_classification/`, executed in order via the `jobs/train_spend_classifier.yml` job:

### `prepare_features.py` — feature engineering + train/holdout split  ✅ DONE

Reads `gold.fact_invoices` joined with `dim_supplier`. Writes three tables to `<catalog>.ml`:

| Table | Approx rows | Purpose |
|---|---|---|
| `spend_clf_train` | ~80% of non-maverick | Stratified 80% per category. Training set. |
| `spend_clf_holdout` | ~20% of non-maverick | Stratified 20% per category. **Excludes** maverick-supplier invoices (kept separately). Used for primary accuracy metric. |
| `spend_clf_maverick_holdout` | Suppliers with `maverick_propensity > 0.15` | The **hard-case eval slice**. Models that pattern-match supplier→category fail here; models that read description + amount + GL account should succeed. |

Stratification by `true_category_secondary` (the leaf) ensures every leaf class has rows in both splits. Deterministic split (seed param). Each row also carries `label_primary` (the parent) so `evaluate.py` can split parent-tier vs. child-tier accuracy without re-joining `dim_spend_category`.

**Widgets**: `catalog`, `schema_gold`, `schema_ml`, `maverick_threshold` (default 0.15), `test_size` (default 0.20), `random_seed` (default 42).

**Diagnostics on run**: row count, full feature schema, top-5 + bottom-5 leaf class distributions, full parent class distribution (all 8 parents), post-split label coverage in train vs. holdout, maverick-slice size warning.

### `train_baseline.py` — TF-IDF + LightGBM, wrapped pyfunc  ✅ DONE

- sklearn `Pipeline` with `ColumnTransformer`:
  - `TfidfVectorizer(ngram_range=(1,2), max_features=20000, sublinear_tf=True, min_df=3)` on `line_description`
  - `OneHotEncoder(handle_unknown="ignore", min_frequency=50, sparse_output=True)` on the 9 categorical columns
  - passthrough on the 4 numeric columns
- `LGBMClassifier(objective="multiclass", n_estimators=300, max_depth=8, num_leaves=63, learning_rate=0.05, class_weight="balanced")`
- Wraps the trained estimator in a `SpendClassifierWithTaxonomy(mlflow.pyfunc.PythonModel)` that:
  - Pulls the leaf→parent map from `<catalog>.gold.dim_spend_category` at training time and bakes it into the model
  - Returns a pandas DataFrame with all four prediction columns
  - Computes `primary_confidence` by summing softmax probabilities over leaves under the predicted parent (via a pre-built membership matrix — vectorized, ~free)
- Logged via `mlflow.pyfunc.log_model` with signature inferred from a sample input/output, registered to `<catalog>.ml.spend_classifier`, alias `@challenger`.

**Widgets**: `catalog`, `schema_ml`, `schema_gold`, `model_name` (default `spend_classifier`), `model_alias` (default `challenger`), `max_train_rows` (default `0` = full training set; set lower for smoke tests).

### `train_embedding.py` — Foundation Model API variant (optional)  ⚠ STUB

- Call `databricks-bge-large-en` via `mlflow.deployments` SDK to embed `line_description` in batches (chunks of 1000).
- Cache embeddings in `<catalog>.ml.spend_clf_embeddings_cache` (keyed by hash of description) so re-runs don't re-embed.
- Train classifier head (logistic regression or 2-layer MLP) on `[embedding ; tabular_features]`.
- MLflow autolog; register as `@challenger_embedding` for comparison.

### `evaluate.py` — slice-level comparison + winner promotion  ✅ DONE

For each model alias (`@challenger`, `@challenger_embedding`, plus a `@gl_account_baseline` lookup model that predicts via `gl_account → most_common_category`):

Recorded labels carry ~8% intra-parent noise (see § 2), so leaf-tier accuracy is capped near 92%. Parent-tier accuracy should approach 100% because noise is intra-parent only.

| Metric | Slice | Target |
|---|---|---|
| **Secondary** (leaf) top-1 accuracy | `spend_clf_holdout` | ≥ 85% (ceiling ~92%) |
| **Primary** (parent) top-1 accuracy | `spend_clf_holdout` | ≥ 98% — the exec-summary number |
| Top-3 leaf accuracy | `spend_clf_holdout` | ≥ 95% |
| Per-leaf F1 | `spend_clf_holdout` | macro-avg ≥ 0.80 |
| **Maverick-slice secondary top-1** | `spend_clf_maverick_holdout` | **≥ 70%** — the headline number for sourcing teams |
| Maverick-slice primary top-1 | `spend_clf_maverick_holdout` | ≥ 88% |
| Confidence calibration (ECE) | `spend_clf_holdout` | ≤ 0.05 |
| GL-account-baseline beat | `spend_clf_holdout` | model must outperform leaf-tier by ≥ 10 pp |

**Implementation:**
- Loads `holdout`, `maverick_holdout`, and `train` (the last only to build the GL-account baseline lookup).
- Discovers which registered aliases exist (`@challenger` always; `@challenger_embedding` if present); silently skips missing aliases.
- Builds the `gl_account → most-common-leaf` baseline in-notebook (no MLflow registration — it's a floor, not a candidate).
- Scores every (model × slice) pair via `mlflow.pyfunc.load_model(...).predict(...)`; the pyfunc returns all four prediction columns natively.
- Writes per-tier metrics to `<catalog>.ml.spend_clf_eval_runs` (appended each run) with `evaluated_at` + `uc_model` provenance columns.
- Promotes the winner — highest `secondary_top1_accuracy` on the maverick slice, ties broken by holdout — to `@production` via `client.set_registered_model_alias(...)`.
- Logs a per-leaf and per-parent `classification_report` for the winning model on the maverick slice (this is the section that goes in the demo deck).
- Warns if the winner's leaf-tier margin over the GL baseline on the maverick slice is < 10 pp.

**Widgets**: `catalog`, `schema_ml`, `schema_gold`, `model_name`.

### `batch_inference.py` — score all `fact_invoices` rows → `ml.invoice_classifications`  ✅ DONE

- Resolves `<catalog>.ml.spend_classifier@production` to a concrete version.
- Reads `gold.fact_invoices` joined with `dim_supplier` (to surface `category_primary_hint`); applies the same log-transforms `prepare_features.py` did. Null categoricals coerced to the `__NA__` sentinel the training pipeline learned.
- Scores via `mlflow.pyfunc.spark_udf(...)` with a `struct<...>` result type — distributed Spark inference, no `toPandas()` roundtrip.
- Flattens the struct into 4 prediction columns + stamps `model_version` (formatted as `<catalog>.<schema>.<model>/v<version>`) + `scored_at = current_timestamp()`.
- MERGEs into `<catalog>.ml.invoice_classifications` keyed by `invoice_line_id` — idempotent.
- Prints coverage + confidence-distribution stats and a parent-category breakdown.
- `gold.fact_invoices` picks predictions up automatically via the LEFT JOIN through `silver.invoice_classification`. No write into the gold fact itself.

**Widgets**: `catalog`, `schema_gold`, `schema_ml`, `model_name`, `model_alias` (default `production`).

> The pyfunc bakes the leaf→parent taxonomy into the model artifact at training time, so the parent tier is derived inside `model.predict()` — no `dim_spend_category` join is needed at inference. If `dim_spend_category` changes shape, old model versions still emit deterministic predictions over their original taxonomy (until the next retraining run).

### `sourcing_strategy_view.py` — the *value* delivered to sourcing  ⚠ STUB

Creates `<catalog>.gold.vw_sourcing_strategy` — a denormalized view that the eventual dashboards / Genie space consume. Filters to `addressability = 'Addressable'` (sourcing can't move regulated spend):

- **Parent-tier concentration**: spend by `predicted_primary_category` × segment × quarter — the exec-summary surface.
- **Leaf-tier supplier share**: within each leaf, Herfindahl index over suppliers for monopsony risk.
- **Maverick spend per leaf**: total $ where `supplier.category_primary != predicted_secondary_category` (supplier shouldn't be selling this).
- **Off-contract category spend**: joined with `silver.contract_inbound` to flag spend that isn't covered by an active inbound contract.
- **Tail spend per segment**: sum of spend in leaves where one segment buys < 5% of company total — candidates for consolidation.

---

## 5. File layout

```
ml/
├── README.md                              ← this file
├── notebooks/
│   └── validate_gold_vs_anchors.py       ← assert gold ties to anchors ±2%
└── spend_classification/                  ← headline ML project
    ├── prepare_features.py               ✅ DONE
    ├── train_baseline.py                 ✅ DONE — TF-IDF + LightGBM, taxonomy-aware pyfunc
    ├── train_embedding.py                ⚠ STUB — Foundation Model API variant (optional)
    ├── evaluate.py                       ✅ DONE — 2-tier metrics + GL baseline + winner promotion
    ├── batch_inference.py                ✅ DONE — spark_udf scoring, MERGE into ml.invoice_classifications
    └── sourcing_strategy_view.py         ⚠ STUB

```

---

## 6. Operational notes

### Job orchestration

`jobs/train_spend_classifier.yml` chains the spend-classification notebooks:

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
- Weekly batch retrain when fresh invoice data is loaded.
- Drift monitoring on the `maverick_propensity` distribution — retrain if it shifts.

### Evaluation transparency

Three deliberate noise sources are baked into the generator. Each is a documented design choice, not a bug:

1. **6% maverick spend** (`_lib.MAVERICK_SPEND_RATE`) — suppliers buying outside their primary category. Drives the `spend_clf_maverick_holdout` slice difficulty.
2. **8% recording noise on invoice lines** (`_lib.LABEL_NOISE_RATE`) — recorded `true_category_secondary` swapped to a sibling within the same parent (Legal mis-recorded as Audit, etc.). Caps leaf-tier accuracy near 92%, parent-tier near 100%. Applied only at invoice-line stamping in `03_fusion_files.py`; PRs and POs are clean.
3. **`gl_account` is a strong but no-longer-perfect signal.** The generator routes GL by the *actual* category (line content is consistent), but the *recorded* label sometimes disagrees — so a `gl_account → most-common-recorded-leaf` lookup hits its ceiling around 88–92%. The model must triangulate `line_description` + `supplier_id` to recover the additional points.

A model that scores 100% holdout is now genuinely impossible against the noisy labels — if you see it, something is leaking (most likely you're evaluating on training data, or the noise wasn't applied in the data regen).

---

## 7. References

- Architecture context: `_demo/00_design_context.md`.
- Data layout & ML signal design: `data/generators/README.md`.
- Taxonomy source of truth: `data/generators/_lib.py` (`SPEND_CATEGORIES`, `SPEND_CATEGORY_HIERARCHY`); UC materialization at `pipelines/reference/gold/dim_spend_category.sql` → `gold.dim_spend_category`.
- Reconciliation parity check: `data/generators/99_reconcile.py` § "(6) Spend-taxonomy parity".
