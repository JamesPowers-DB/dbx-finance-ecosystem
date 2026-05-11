# `data/generators/` — Helios synthetic data generators

Anchor-driven data generators that synthesize raw source-system files for the Helios Industrial Group demo. Numbers are anchored to a reference public industrial conglomerate's 10-K/10-Q filings scaled 1/10 (see `_demo/00_design_context.md`).

## Notebook map

| Notebook | Output | Purpose |
|---|---|---|
| `_lib.py` | (shared helpers, `%run` source) | Seeds, spend taxonomy, anchor/macro readers, volume + widget helpers |
| `00_macro_environment.py` | `gold.dim_macro_environment` (Delta) | Monthly macro factors (GDP arc + AR(1) noise + inflation, demand, supply stress, labor, seasonality) |
| `01_period_anchors_seed.py` | `_meta.dim_period_anchors` + `dim_period_anchors_draft` (Delta) | Hand-curated baseline rows for FY23, FY24, Q1–Q3 2025 |
| `02_ariba_files.py` | `sap_ariba/*.csv` | LFA1 supplier master + Ariba contract workspace + sourcing events + per-quarter EKKO / EKPO / RBKP / supplier scorecard |
| `03_fusion_files.py` | `oracle_fusion/*.{csv,parquet}` | COA + supplier/customer sites + per-quarter GL JE headers/lines / AP / AR / trial balance / balances |
| `04_cms_files.py` | `inhouse_cms/*.jsonl` | Outbound contracts + parties + line items + amendments + performance obligations + per-quarter billing schedule |
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
└── filings/raw/
    └── 10q_<YYYY>q<q>.html                     (10-Q drops)
```

---

## Spend classification — what's in the data for ML

The Ariba generator embeds these signals so a Phase 2 spend-classification model has something interesting to learn:

- **30 spend categories** with segment affinity (HAD / HPA / HSB / HET / CROSS), defined in `_lib.SPEND_CATEGORIES`.
- **`LFA1._supplier_category_primary`** — 70% suppliers have one primary category; many have 1–2 secondary categories.
- **`LFA1._maverick_propensity`** (0–0.3 beta-distributed) — drives the rate of off-category purchases per supplier.
- **`EKPO.MATGROUP`** — coarse SAP material-group code. 8% noisy (assigned to the wrong category) so the model has to outperform MATGROUP-only baselines.
- **`EKPO.TXZ01`** — free-text line description built from category-specific noun / adjective / "extra" pools, with shared vocabulary across related categories. ~5,000 unique templates across the 30 categories.
- **`EKPO.NETPR` / `MENGE` / `MEINS`** — price / qty / UoM log-normal per category. Raw materials are cheap & high-volume; consulting is expensive & low-volume.
- **`EKPO._true_spend_category`** — **demo-only ground-truth label**. Represents the "manual categorization step" that exists in real systems via category managers + supplier-master fields. Bronze keeps it; silver propagates it. The Phase 2 classification model is trained to predict the future `fact_spend.unspsc_family_code` from `MATNR` + `TXZ01` + `LIFNR` + `NETWR` + `cost_center`, with `_true_spend_category` as the supervised label.

Suggested model evaluation slice: hold out maverick POs (`supplier._maverick_propensity > 0.15`) and compare accuracy against in-policy POs to demonstrate the model catches off-pattern spend.

---

## Future 10-Q ingestion workflow

The whole demo is designed to grow as new reference 10-Qs are released. To add a quarter:

### 1. Drop the filing

Upload the 10-Q HTML to:

```
/Volumes/finance_demo/raw_data/files/filings/raw/10q_<YYYY>q<q>.html
```

E.g. `10q_2026q1.html`. Download the source filer's 10-Q HTML from their investor-relations site and save it locally.

### 2. Run the ingestion job

```bash
databricks bundle run ingest_10q -t dev \
  --params filing_path=/Volumes/finance_demo/raw_data/files/filings/raw/10q_2026q1.html,fiscal_year=2026,fiscal_quarter=1
```

This runs three tasks in order:

| Task | Notebook | What it does |
|---|---|---|
| `extract_10q` | `ml/notebooks/01_extract_10q.py` | `ai_extract` / `AI_QUERY` (Claude) parses the HTML into a draft row per segment + CONSOL → writes to `_meta.dim_period_anchors_draft` with a `confidence_score` |
| `review_anchor_draft` | `ml/notebooks/02_review_anchor_draft.py` | Human-in-the-loop notebook. Shows draft vs. prior quarter diff; you confirm the 1/10 scaling + Helios segment renames; on accept it `MERGE`s into `_meta.dim_period_anchors` |
| `regenerate_quarter` | `ml/notebooks/03_regenerate_quarter.py` | Re-runs `02_ariba_files.py`, `03_fusion_files.py`, `04_cms_files.py` with `target_fiscal_year` + `target_fiscal_quarter` set → only that quarter's per-quarter files are rewritten. Stable files (supplier master, contracts, COA) are not touched. |

### 3. Rebuild the lakehouse

```bash
databricks bundle run build_lakehouse -t dev
```

The Lakeflow pipeline picks up the new quarter's files (Auto Loader / incremental DLT), propagates through silver → gold. `ml/notebooks/99_validate_gold_vs_anchors.py` runs as the final task and asserts the gold facts tie back to the new anchor row.

### Why hybrid (AI extract + human review)?

Pure AI extraction is fast but creates trust debt — a hallucinated $200M shift in COGS would silently propagate into every dashboard and ML training set. The human-review gate costs ~10 minutes per quarter but gives a reproducible, auditable anchor history. The review step itself is a demoable moment for the Wave 1 narrative (AI extraction + human-in-the-loop = trustworthy automation).

### What if I want to backfill multiple quarters?

Run `ingest_10q` once per quarter, accepting each draft before moving to the next. Anchors form an append-only audit trail; the regenerator works one quarter at a time.

### What if numbers change historically (source filer restates)?

Update the relevant row in `_meta.dim_period_anchors` directly, then run `03_regenerate_quarter.py` with the affected quarter. The generators are idempotent — re-running just overwrites the quarter's files.

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
