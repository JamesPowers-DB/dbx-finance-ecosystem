# `data/generators/` — Helios synthetic data generators

Anchor-driven data generators that synthesize raw source-system files for the Helios Industrial Group demo. Numbers are anchored to hand-curated rows in `_meta.dim_period_anchors` (1/10-scaled from a reference public industrial conglomerate's filings — see `_demo/00_design_context.md`).

## Notebook map

| Notebook | Output | Purpose |
|---|---|---|
| `_lib.py` | (shared helpers, `%run` source) | Seeds, spend taxonomy, anchor/macro readers, volume + widget helpers |
| `00_macro_environment.py` | `gold.dim_macro_environment` (Delta) | Monthly macro factors (GDP arc + AR(1) noise + inflation, demand, supply stress, labor, seasonality) |
| `01_period_anchors_seed.py` | `_meta.dim_period_anchors` (Delta) | Hand-curated baseline rows: FY23, FY24, Q1–Q4 2025 + FY25 consolidated, Q1 2026. Add a tuple to `CONSOL_PERIODS` to extend. |
| `02_ariba_files.py` | `sap_ariba/*.csv` | LFA1 supplier master + Ariba contract workspace + sourcing events + per-quarter EKKO / EKPO / RBKP / supplier scorecard |
| `03_fusion_files.py` | `oracle_fusion/*.{csv,parquet}` | COA + supplier/customer sites + per-quarter GL JE headers/lines / AP / AR / trial balance / balances |
| `04_cms_files.py` | `inhouse_cms/*.jsonl` | Outbound contracts + parties + line items + amendments + performance obligations + per-quarter billing schedule |
| `05_workday_workers.py` | `workday/workers.csv` | Workday-shaped employee SCD Type 2 history. Active-worker count per (fy, fq, segment) tracks anchor `headcount_total`. Drives `gold.dim_employees` → `gold.fact_emp_quarterly_cost`. |
| `99_reconcile.py` | (assertion only) | Verifies Ariba spend, CMS revenue, and Fusion GL balance vs. anchors. Fails the job on breach. |

## How the anchoring works

```
                          _meta.dim_period_anchors  (5 segs × 5 periods seeded)
                                      │
                                      ▼
                       (target totals per fy × fq × segment)
                                      │
                                      ▼
                  ┌───────────────────┴───────────────────┐
                  │                                       │
          02_ariba_files.py                       04_cms_files.py
       (spend = cogs + sga + rd)                (revenue side)
                  │                                       │
                  └───────────────────┬───────────────────┘
                                      ▼
                              03_fusion_files.py
                         (GL mirrors AP + AR; balanced)
                                      │
                                      ▼
                              99_reconcile.py
                       (asserts ±2% spend, ±2% revenue,
                        strict per-JE balance == 0)
```

Within each quarter, monthly distribution is shaped by `gold.dim_macro_environment` (demand × seasonality × supply-stress), then **renormalized** so the quarterly sum equals the anchor exactly. Per-transaction noise stays bounded so the empirical sum drifts under ±2%.

## Determinism

Every generator derives its rng / Mimesis seeds from `_lib.derive_seed("<label>")` keyed off `MASTER_SEED = 42`. Re-running a single notebook always produces the same output for the same anchor + macro inputs. To change the data, edit the anchor table or `MASTER_SEED`.

## Volume layout

All raw files land in the single managed volume `raw_data.files`:

```
/Volumes/finance_demo/raw_data/files/
├── sap_ariba/
│   ├── LFA1_SUPPLIER_MASTER.csv                (stable; 3,000 rows)
│   ├── ARIBA_CONTRACT_WORKSPACE.csv            (stable; ~1,500 rows)
│   ├── ARIBA_SOURCING_EVENT.csv                (stable; ~2,500 rows)
│   ├── EKKO_PO_HEADER_<YYYYQq>.csv             (per quarter)
│   ├── EKPO_PO_LINE_<YYYYQq>.csv               (per quarter; ML training payload)
│   ├── RBKP_INVOICE_HEADER_<YYYYQq>.csv        (per quarter)
│   └── ARIBA_SUPPLIER_PERFORMANCE_<YYYYQq>.csv (per quarter)
├── oracle_fusion/
│   ├── gl_periods.csv                          (stable)
│   ├── gl_code_combinations.csv                (stable)
│   ├── ap_supplier_sites_all.csv               (stable)
│   ├── ar_customer_sites_all.csv               (stable)
│   ├── gl_je_headers_<YYYYQq>.csv              (per quarter)
│   ├── gl_je_lines_<YYYYQq>.parquet            (per quarter)
│   ├── gl_trial_balance_<YYYYQq>.csv
│   ├── gl_balances_<YYYYQq>.parquet
│   ├── ap_invoices_all_<YYYYQq>.csv
│   ├── ap_invoice_distributions_all_<YYYYQq>.parquet
│   └── ar_invoices_all_<YYYYQq>.csv
├── inhouse_cms/
│   ├── _customer_pool.jsonl                    (stable internal pool)
│   ├── contract.jsonl                          (stable; ~5,000 rows)
│   ├── contract_party.jsonl                    (stable)
│   ├── contract_line_item.jsonl                (stable)
│   ├── contract_amendment.jsonl                (stable)
│   ├── performance_obligation.jsonl            (stable)
│   └── billing_schedule_<YYYYQq>.jsonl         (per quarter)
```

---

## Spend classification — what's in the data for ML

The generators embed these signals so the spend-classification model has something interesting to learn:

- **2-tier spend taxonomy** — 8 parents × 30 leaves with segment affinity (HAD / HPA / HSB / HET / CROSS). Source of truth: `_lib.SPEND_CATEGORIES` + `_lib.SPEND_CATEGORY_HIERARCHY`. UC mirror: `gold.dim_spend_category`.
- **`LFA1._supplier_category_primary`** — 70% suppliers have one primary category; many have 1–2 secondary categories.
- **`LFA1._maverick_propensity`** (0–0.3 beta-distributed) — drives the rate of off-category purchases per supplier.
- **`EBAN.MATGROUP`** / **PO `material_group_code`** — coarse SAP material-group code. 8% noisy (assigned to the wrong category) so the model has to outperform MATGROUP-only baselines.
- **`EBAN.TXZ01`** / **invoice `item_description`** — free-text line description built from category-specific noun / adjective / "extra" pools, with shared vocabulary across related categories. ~5,000 unique templates across the 30 leaves.
- **`PREIS` / `MENGE` / `MEINS` (and downstream amount/quantity/unit_price)** — log-normal per category. Raw materials are cheap & high-volume; consulting is expensive & low-volume.
- **`_true_category_primary` + `_true_category_secondary`** — **demo-only ground-truth labels** stamped on PR / PO / invoice lines. Represents the "manual categorization step" that exists in real systems via category managers + supplier-master fields — **in production these columns wouldn't exist on operational data**; the customer would supply a hand-curated training set. For the demo they're propagated through silver/gold so the classifier has a deterministic supervised signal. The model trains on the leaf (`true_category_secondary`); inference output (`ml.invoice_classifications`) carries both predicted tiers.

Suggested model evaluation slice: hold out maverick invoices (`supplier._maverick_propensity > 0.15`) and compare accuracy against in-policy invoices to demonstrate the model catches off-pattern spend. See `ml/README.md` § 4 — Evaluation for the full eval rubric.

---

## Extending the demo to new quarters

Anchors live as hand-curated tuples in `01_period_anchors_seed.py:CONSOL_PERIODS`. To add a quarter:

1. Add a new tuple (period_type, fy, fq, period_end, revenue, cogs, sga, rd, op_inc, ...). Keep numbers in the same `~1/10 of the reference industrial` scale as the existing rows so the storyline holds.
2. Re-run `databricks bundle run generate_data -t dev` — the generators pick up every quarter present in `dim_period_anchors` and synthesize new per-source files for the added period(s). Existing quarters are not touched.
3. Refresh the lakehouse pipeline so bronze/silver/gold pick up the new files.

The generators are idempotent — re-running just overwrites the affected quarter's files. If reference numbers ever change historically, edit the row in `CONSOL_PERIODS` and re-run.

Earlier iterations of this demo had an AI-extracts-10Q-HTML workflow (`extract_10q.py` / `review_anchor_draft.py` / `regenerate_quarter.py`). It was removed because the indirection added complexity without changing what gets demoed. If a customer wants to see AI-extraction-from-filings, that's better as its own demo using `ai_query` / `ai_extract` on a single page.

---

## Standalone testing (off-Databricks)

The generators are written as Databricks notebooks but their core logic (Polars + NumPy + Mimesis) runs anywhere. To test a generator outside Databricks:

```bash
# 1. Comment out the `%run ./_lib` line and the `dbutils.widgets.*` calls
# 2. Hardcode the catalog / schema / volume widget values
# 3. Run:
uv run --with polars --with numpy --with mimesis \
       --with "databricks-connect>=16.4,<17.0" \
       data/generators/02_ariba_files.py
```

The notebook references `spark` (auto-injected on Databricks) and `dbutils.widgets`; outside Databricks you'd swap to `DatabricksSession.builder.serverless().getOrCreate()` and a manual widget dict.

In normal operation, all generators run as job tasks via:

```bash
databricks bundle run generate_data -t dev
```
