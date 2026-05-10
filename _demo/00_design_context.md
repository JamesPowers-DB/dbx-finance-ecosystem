# Demo Design Context — `dbx-finance-ecosystem`

> **Purpose of this file:** persistent design context for the rebuild of the finance data ecosystem demo. Load this at the start of any new conversation so the next step (scaffolding the project structure with Claude skills) starts with full architectural alignment.

---

## Origin

- **Owner:** James Powers (FE SA, Databricks)
- **Initiative:** FY26 Horizontal GTM Wave 1: F-1 Finance — Spend Visibility & Strategic Sourcing Intelligence
- **Target:** dbdemos Gold-tier status
- **Predecessor repo:** `~/Dev/fin_demo` (existing, stale, source-system-agnostic) — reference only, not the target
- **This repo:** `~/Dev/dbx-finance-ecosystem` (clean rebuild starting from empty repo)
- **Design doc:** <https://docs.google.com/document/d/1NbkfiV-4dVe4xOr0uiBCGJ5NvYKtxS5xTEBwtuXR5ug/edit>

---

## Three explicit user requirements

1. **Data realism via Honeywell anchoring.** Use Honeywell's 10-K + 10-Q as a numerical anchor; **fully anonymize** company name/segments/geographies; scale numbers ~1/10 so the demo company reads as a mid-cap industrial conglomerate.
2. **Future 10-Q ingestion.** When a new 10-Q drops, the user should be able to upload the HTML and have new quarter records generated that reconcile to the filing.
3. **Three source-system shapes.** Raw bronze data must look like it came from SAP Ariba (procurement), Oracle Fusion Cloud (accounting), and a custom in-house contract management system (CMS).

**Honeywell source filings:**
- 10-K: <https://investor.honeywell.com/node/50761/html>
- Latest 10-Q: <https://investor.honeywell.com/node/51331/html>

---

## User decisions (captured via AskUserQuestion)

| Decision area | Chosen option |
|---|---|
| Anonymized company + segments | **Helios Industrial Group (HIG)** with segments HAD / HPA / HSB / HET |
| 10-Q ingestion workflow | **Hybrid: AI-extract draft + human review + commit** |
| Geographies | **NA / EMEA / APAC / LATAM** (rename, not retained verbatim) |
| Catalog/schema layout | **`finance_demo.{raw_data, bronze_ariba, bronze_fusion, bronze_cms, silver, gold, _meta, ml}`** (expanded from 6 → 8 schemas during scaffold; see §10) |

---

## 1. Anonymized company framing

**Company:** Helios Industrial Group, Inc. (HIG)
**Fiscal year:** calendar-year (Dec 31 close), preserving Honeywell's cadence
**Scale:** 1/10 of Honeywell — ~$3.85B FY revenue, ~$570M net income, ~10K employees

| Helios segment                            | Code | HON segment origin                | Mix |
|-------------------------------------------|------|-----------------------------------|-----|
| Helios Aerospace & Defense                | HAD  | Aerospace Technologies            | ~37% |
| Helios Process Automation                 | HPA  | Industrial Automation             | ~26% |
| Helios Smart Buildings                    | HSB  | Building Automation               | ~16% |
| Helios Energy Transition                  | HET  | Energy & Sustainability Solutions | ~21% |

**Geographies:** `North America` (~60%), `EMEA` (~22%), `APAC` (~13%), `LATAM` (~5%).

**Working-capital shape (post-1/10 scaling):** ~$800M AR, ~$600M inventory, ~$600M AP, ~$2.5B long-term debt, ~$1.0B cash.

---

## 2. Anchor table — `_meta.dim_period_anchors`

Single source of truth for "what does Helios's books look like in period X." All downstream generators reconcile to it.

**Grain:** one row per (`period_type`, `period_end_date`, `segment_code`)
- `period_type ∈ {'FY','Q'}`
- `segment_code ∈ {'HAD','HPA','HSB','HET','CONSOL'}`
- Segment rows sum to CONSOL within rounding.

**Columns:**

- **Identity:** `period_type`, `fiscal_year`, `fiscal_quarter` (NULL on FY rows), `period_end_date`, `segment_code`, `segment_name`
- **P&L (USD millions):** `revenue`, `cogs`, `gross_profit`, `sga`, `rd`, `operating_income`, `interest_expense`, `tax_provision`, `net_income`
- **Balance sheet (CONSOL only):** `cash`, `ar`, `inventory`, `ap`, `lt_debt`, `total_assets`, `total_equity`
- **Cash flow (CONSOL only):** `operating_cash_flow`, `capex`, `free_cash_flow`
- **Headcount:** `headcount_total` (CONSOL + per-segment when disclosed)
- **Provenance:** `source_filing_type` (`10-K`|`10-Q`), `source_filing_url`, `source_extracted_at`, `human_reviewed_by`, `human_reviewed_at`, `confidence_score`, `notes`

**Initial seeding:** hand-curated rows for FY2023, FY2024, plus each available quarterly period from the most recent 10-Q, with 1/10 scaling and Helios-segment naming applied at load time.

### 10-Q ingestion workflow (hybrid AI + human-review)

1. **Drop:** user uploads new 10-Q HTML to `/Volumes/finance_demo/raw_data/files/filings/raw/10q_<period>.html`.
2. **Extract:** an *extractor notebook* runs `ai_extract` / `AI_QUERY` over the HTML using Claude with a strict JSON schema matching the anchor columns. Writes a draft row (per segment + CONSOL) to `_meta.dim_period_anchors_draft` with a `confidence_score`.
3. **Review:** a *review notebook* diffs draft vs. prior quarter (QoQ deltas, segment-to-CONSOL tie-out, sign checks, scaling-applied check). User stamps `human_reviewed_by` and merges into `_meta.dim_period_anchors`.
4. **Regenerate:** a *regenerate_quarter* notebook detects the new accepted anchor row(s), re-runs the source-system generators for that quarter only, and re-publishes the affected silver/gold partitions.

This workflow itself is demoable (AI extraction + human-in-the-loop) for the Wave 1 narrative.

---

## 3. Source-shaped bronze design

**Layout:** three per-source schemas under one catalog, all reading files from a single managed volume in `raw_data` (per skill convention — keeps all raw files in one place; bronze schemas hold the Delta tables that read from there).

Volume layout:
```
/Volumes/finance_demo/raw_data/files/
├── sap_ariba/        CSV exports
├── oracle_fusion/    CSV + Parquet
├── inhouse_cms/      line-delimited JSON
└── filings/raw/      10-Q HTML for anchor extraction
```

### `bronze_ariba` — SAP Ariba procurement (CSV exports)

SAP ALL_CAPS + German codes preserve native flavor:

| Table | Key fields |
|---|---|
| `LFA1_SUPPLIER_MASTER` | `LIFNR`, `NAME1`, `LAND1`, `ERSDA`, `SPRAS` |
| `EKKO_PO_HEADER` | `EBELN`, `BUKRS`, `LIFNR`, `BSART`, `AEDAT` |
| `EKPO_PO_LINE` | `EBELN`, `EBELP`, `MATNR`, `MENGE`, `NETPR`, `WAERS` |
| `RBKP_INVOICE_HEADER` | `BELNR`, `LIFNR`, `BUKRS`, `BLDAT`, `WRBTR` |
| `ARIBA_SOURCING_EVENT` | `EventId`, `EventType` (RFQ/RFP/Auction), `CreatedOn`, `SupplierInvitedCount` |
| `ARIBA_CONTRACT_WORKSPACE` | `ContractWorkspaceId`, `ContractType`, `EffectiveDate`, `ExpirationDate`, `TotalCommittedSpend` |
| `ARIBA_SUPPLIER_PERFORMANCE` | quarterly scorecard rows |

Document number prefixes: `PO-`, `INV-`, `SRC-`.

### `bronze_fusion` — Oracle Fusion Cloud accounting (CSV + Parquet from BIP)

Oracle snake_case with classic table prefixes:

- `gl_je_headers`, `gl_je_lines`, `gl_code_combinations` — 7-segment COA: entity / cost_center / natural_account / product / intercompany / future1 / future2
- `gl_periods`, `gl_balances`, `gl_trial_balance`
- `xla_ae_headers`, `xla_ae_lines` — subledger accounting
- `ap_invoices_all`, `ap_invoice_distributions_all`, `ap_payment_schedules_all`, `ap_supplier_sites_all`
- `ar_invoices_all`, `ar_receipt_schedules`, `ar_customer_sites_all`

### `bronze_cms` — In-house contract management (line-delimited JSON)

Clean snake_case, flat, no exotic prefixes:

- `contract` — `contract_id`, `contract_number`, `customer_id`, `segment_code`, `signed_date`, `start_date`, `end_date`, `total_contract_value`, `currency`, `status`
- `contract_party`
- `contract_line_item`
- `contract_amendment`
- `performance_obligation`
- `billing_schedule`

Three different file formats (CSV / Parquet / JSON) create visible source diversity in lineage views.

---

## 4. Silver and Gold (conceptual)

### Silver — single schema `finance_demo.silver`

Canonical conformed entities. Each row carries `source_system`, `source_table`, `source_primary_key` for lineage.

- `silver.supplier` (union of Ariba `LFA1` + Fusion `ap_supplier_sites_all`; `supplier_canonical_id` column reserved)
- `silver.customer`
- `silver.purchase_order`
- `silver.invoice_ap`
- `silver.invoice_ar`
- `silver.contract_outbound` (from CMS)
- `silver.contract_inbound` (from Ariba)
- `silver.gl_journal_entry`, `silver.gl_journal_line`
- `silver.coa_account`
- `silver.sourcing_event`

### Gold — single schema `finance_demo.gold`

Preserves old demo's analytical surface; reserves Phase 2 hooks.

**Facts:** `fact_spend`, `fact_revenue`, `fact_gl_entries`, `fact_trial_balance`, `fact_fpa_actuals`, `fact_fpa_budgets`, `fact_fpa_forecasts`, `fact_emp_quarterly_cost`

**Dims:** `dim_supplier`, `dim_customer`, `dim_segment`, `dim_cost_center`, `dim_account`, `dim_date`, `dim_macro_environment`

**Reserved Phase 2 columns** (nullable now, populated later):

| Table | Reserved columns |
|---|---|
| `fact_spend` | `managed_spend_flag`, `unspsc_segment_code`, `unspsc_family_code`, `supplier_canonical_id`, `classification_confidence` |
| `dim_supplier` | `canonical_supplier_id`, `entity_resolution_cluster_id` |
| `fact_revenue` | `contract_leakage_flag`, `savings_realized_usd` |

**Reserved empty dim shells:** `dim_unspsc_taxonomy`, `dim_supplier_canonical`

`_meta.dim_period_anchors` is exposed read-only to gold consumers via a view for dashboards.

---

## 5. Reconciliation strategy

**Top-down constraint:** for every (`fiscal_year`, `fiscal_quarter`, `segment_code`) tuple with a row in `dim_period_anchors`, synthetic transactions must aggregate to **within ±2% of the anchor** for primary metrics — segment revenue and segment-mapped spend (COGS + SG&A + R&D).

**Generator pattern:**

1. Read anchor totals for target (quarter × segment).
2. **Allocate to months** using macro AR(1) factors from old `fin_demo` TASKS.md (`seasonality_idx × demand_idx_sales` for revenue; `seasonality_idx × demand_idx_mfg × supply_chain_stress_idx` for spend) — **normalized** so monthly buckets sum exactly to the quarter anchor.
3. **Draw transactions** within each month from a distribution that integrates to the monthly target. Per-transaction noise bounded so empirical sums stay within tolerance.
4. **Master seed:** deterministic `numpy.random.default_rng(42)` with per-generator sub-seeds.

**Tie-out gate:** a dedicated reconciliation notebook runs after all generators and **fails the job** if any anchor metric drifts beyond ±2%. Enforced contract, not spot-check.

**Trade-off captured:** old demo's macro factors ran free → totals drifted (the staleness). New approach uses macro factors only for *shape within a quarter*; totals are pinned to anchors.

---

## 6. Out of scope for foundation (Phase 2+ hooks already reserved)

Deferred but additive — schema reserves columns/shells:

- UNSPSC taxonomy + spend classification ML
- Supplier entity resolution
- Contract leakage / maverick spend detection
- Savings tracking
- Managed-spend metrics
- Lakebase supplier-master app
- Genie spaces with synonyms
- Autonomous agents
- Dashboards (Executive, FinOps)
- AI_FORECAST / AI_QUERY consumption assets
- Demo script rewrite, pitch deck, dbdemos packaging

---

## 7. Verification approach

End-to-end smoke test:

1. **Anchor load:** `_meta.dim_period_anchors` contains seeded rows for FY2023, FY2024, and Q1'25 → latest Q.
2. **Source-shape sanity:** browse `bronze_ariba` / `bronze_fusion` / `bronze_cms` in catalog explorer; names read as SAP / Oracle / in-house.
3. **Volume layout:** `/Volumes/finance_demo/raw_data/files/sap_ariba/EKKO_PO_HEADER/<load_date>/` exists with CSVs; analogous `/oracle_fusion/` (Parquet/CSV), `/inhouse_cms/` (JSON), and `/filings/raw/` for 10-Q HTML.
4. **Reconciliation gate:** build job runs; tie-out notebook passes — for each (FY, Q, segment) with an anchor row, gold facts land within ±2%.
5. **10-Q replay:** drop a "next quarter" HTML, run extractor → review → regenerate; gold facts grow by exactly one quarter and tie out.
6. **Anonymization check:** grep all generated content — no occurrences of `Honeywell`, `HON`, `Aerospace Technologies`, `Industrial Automation`, `Building Automation`, `Energy and Sustainability`. Honeywell's literal `US / Europe / Other International` geographic phrasing also banned (country fields in supplier addresses can stay realistic).

---

## 8. Critical files / references

- `~/Dev/dbx-finance-ecosystem/` — target repo (this rebuild)
- `~/Dev/fin_demo/databricks.yml` — reference bundle structure (evolve from)
- `~/Dev/fin_demo/TASKS.md` — reference for macro-environment AR(1) pattern & deterministic seeds
- `~/Dev/fin_demo/00.Data Generation/00a_generate_macro_environment.ipynb` — reference macro factor generation
- Honeywell 10-K: <https://investor.honeywell.com/node/50761/html>
- Honeywell 10-Q: <https://investor.honeywell.com/node/51331/html>
- Design doc: <https://docs.google.com/document/d/1NbkfiV-4dVe4xOr0uiBCGJ5NvYKtxS5xTEBwtuXR5ug/edit>
- Approved plan: `~/.claude/plans/check-out-this-design-compiled-pond.md`

---

## 9. Next planning step

The DAB scaffold is now in place (see `databricks.yml`, `resources/`, `jobs/`, `pipelines/`, `data/generators/`, `ml/notebooks/`). All SQL files and notebooks are stubs with TODO comments — the structure is final, the *content* is next.

Next step applies these skills against the scaffold:

- `fe-databricks-tools:databricks-data-generation` — populate `data/generators/02_ariba_files.py`, `03_fusion_files.py`, `04_cms_files.py` with anchor-driven Polars/Mimesis synthesis. Also populate `01_period_anchors_seed.py` with Honeywell baseline values.
- `fe-databricks-tools:databricks-resource-deployment` — populate bronze/silver/gold pipeline SQL files; deploy the bundle.

Implementation order:
1. Period anchor seed (`01_period_anchors_seed.py`) — produces the canonical truth.
2. Macro environment generator (`00_macro_environment.py`) — produces the within-quarter shape.
3. Per-source file generators (Ariba → Fusion → CMS) — produce raw files reconciled to anchors.
4. Reconciliation gate (`99_reconcile.py`) — asserts ±2% tie-out before pipeline run.
5. Bronze SQL — Auto Loader DLT declarations per source system.
6. Silver SQL — conformed canonical entities.
7. Gold SQL — facts + dims with Phase 2 hooks reserved.
8. Gold-vs-anchor validator (`99_validate_gold_vs_anchors.py`) — final tie-out after pipeline runs.
9. 10-Q ingestion notebooks (`01_extract_10q.py`, `02_review_anchor_draft.py`, `03_regenerate_quarter.py`).

## 10. Reconciliations vs. original architecture (made during scaffold)

The `dbx-bundle-medallion-project` skill prescribed a few conventions that triangulated against the original 6-schema design. Changes made:

| Change | Reason |
|---|---|
| Added `raw_data` schema with a single managed volume `files/` | Skill convention — keep all raw files in one volume keyed by `<source>/` subdir; bronze schemas read from there. Cleaner than per-bronze-schema volumes. |
| Volume path changed from `/Volumes/finance_demo/<bronze>/raw/...` to `/Volumes/finance_demo/raw_data/files/<source>/...` | Follows from above. 10-Q HTML now lives at `raw_data/files/filings/raw/`. |
| Added `ml` schema | Skill convention — explicit home for Phase 2 ML feature tables + registered models. |
| One Lakeflow pipeline (`lakehouse`) instead of multiple per-domain pipelines | Skill convention. Old `fin_demo` had 8 per-domain DLT pipelines; new design uses one pipeline with explicit library list. Easy to split later if needed. |
| SQL-first transformation language (was Python in `fin_demo`) | dbdemos Gold-tier requirement ("Prefer SQL over Python") + skill convention. |
| Pipeline default schema = `silver`; bronze + gold qualified explicitly in SQL | Single pipeline writes to many schemas; default schema is for the most-used layer. |
| Targets: `dev` (default, `aws-e2-demo-field-eng` profile) + `prod` (`e2-demo-west` host) | Carried forward from old `fin_demo`. Skill suggests prod-only but explicitly allows dev for active iteration. |

The architecture in §1–§8 is otherwise unchanged. Schema count went from 6 → 8 (added `raw_data` and `ml`), and the volume location for 10-Q HTML moved one level.
