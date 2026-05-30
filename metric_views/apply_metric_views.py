# Databricks notebook source
# ============================================================================
# apply_metric_views — create/refresh the UC metric layer
# ============================================================================
# Metric views (CREATE VIEW ... WITH METRICS LANGUAGE YAML) are NOT valid
# Lakeflow Spark Declarative Pipeline datasets, so they can't live in the
# lakehouse pipeline. This notebook is the bundle-managed, reproducible way to
# (re)create them — run it as a post-pipeline job task (jobs/apply_metric_views.yml)
# after the lakehouse refresh.
#
# Architecture (subject-scoped, no logic duplication, no extra materialized view):
#   gold.mv_spend                 base — STRAIGHT TABLE SOURCE over gold.fact_invoices
#                                 (no source query, no joins — the fact already
#                                 carries every column). The governed per-line
#                                 conditions live inline in the measure expressions.
#   gold.mv_supplier_performance  parties subject — NESTS on gold.mv_spend
#                                 (source: <catalog>.gold.mv_spend) and re-projects
#                                 the supplier-grain slice. Inherits all measures.
#
# MANAGED SPEND IS LINEAGE-TRUE:
#   contract_id / sourcing_event_id are stamped on the PR (by value threshold +
#   compliance) and ride PR→PO→invoice, so on fact_invoices they're plain columns.
#   The managed-spend conditions are simple presence checks inline in each measure
#   (contract_id IS NOT NULL / sourcing_event_id IS NOT NULL) — NO source query,
#   NO joins, no semi-joins, no fan-out. (This replaced the EXISTS/IN supplier-level
#   heuristic that was the root cause of the inflated coverage.)
#
# Managed Spend = contracted OR competitively sourced. Deliberately NOT PO-match
# (a PO can be cut to any off-contract supplier — that's AP hygiene, surfaced
# separately as PO Coverage Pct). Coverage is dollar-weighted; count-weighted
# companions (… Pct (count)) expose the divergence — managed spend is a small
# count of large buys.
#
# Ratio measures are stored as natural fractions (0–1) and rendered via a
# `format: percentage` spec (which multiplies by 100 for display). Spend
# measures carry a USD currency format.
#
# Requires DBR 17.2+ (serverless tracks latest). Idempotent (CREATE OR REPLACE).
# ============================================================================

dbutils.widgets.text("catalog", "horizontal_finance_dev")
dbutils.widgets.text("schema_gold", "gold")
dbutils.widgets.text("schema_silver", "silver")

catalog = dbutils.widgets.get("catalog")
gold = dbutils.widgets.get("schema_gold")
silver = dbutils.widgets.get("schema_silver")

fq_gold = f"`{catalog}`.`{gold}`"

# ── Base: gold.mv_spend ──────────────────────────────────────────────────────
# Straight table source over gold.fact_invoices — the per-line conditions live
# inline in the measure expressions. Catalog/schema are interpolated so the same
# definition deploys to dev and prod unchanged.
mv_spend = f"""
CREATE OR REPLACE VIEW {fq_gold}.mv_spend
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1

source: horizontal_finance_dev.gold.fact_invoices

comment: "Spend semantic + metric layer over gold.fact_invoices (straight table source\
  \ — fact_invoices already carries every column needed, so no source query and no\
  \ joins). The governed per-line conditions (paid / addressable / contracted / sourced\
  \ / po-matched / classified) live inline in the measure expressions. Managed = contracted\
  \ OR competitively sourced (NOT PO-match). Base for mv_supplier_performance."

dimensions:
  - name: invoice_date
    expr: invoice_date
    comment: "AP invoice line date. Filter >= date_sub(current_date,365) for trailing-12-month\
      \ views."
    display_name: Invoice Date
    synonyms:
      - invoice date
      - date
  - name: payment_date
    expr: payment_date
    display_name: Payment Date
    synonyms:
      - payment date
      - pay date
  - name: fiscal_year
    expr: fiscal_year
    display_name: Fiscal Year
    synonyms:
      - fy
      - year
  - name: fiscal_quarter
    expr: fiscal_quarter
    display_name: Fiscal Quarter
    synonyms:
      - fq
      - quarter
  - name: segment
    expr: segment_code
    comment: business segment (AD / PA / SB / ET / CORP).
    display_name: Segment
    synonyms:
      - business segment
      - division
      - business unit
  - name: category_primary
    expr: true_category_primary
    comment: Parent spend category (8-way taxonomy).
    display_name: Category Primary
    synonyms:
      - spend category
      - parent category
      - category
  - name: category_secondary
    expr: true_category_secondary
    comment: Leaf spend category (30-way taxonomy).
    display_name: Category Secondary
    synonyms:
      - leaf category
      - subcategory
  - name: addressability
    expr: addressability
    comment: Addressable (sourcing can act) vs Non-Addressable (regulated supplier).
    display_name: Addressability
    synonyms:
      - addressable
  - name: direct_or_indirect
    expr: direct_indirect
    display_name: Direct or Indirect
    synonyms:
      - spend type
      - direct vs indirect
  - name: pr_source
    expr: "COALESCE(pr_source, 'Non-PO Voucher')"
    comment: Origination channel of the purchase request (Catalog / AribaPortal /
      ManualSubmission / ProcurementAgent). 'Non-PO Voucher' = direct voucher with
      no PR.
    display_name: PR Source
    synonyms:
      - origination channel
      - purchase channel
      - requisition source
  - name: is_managed
    expr: contract_id IS NOT NULL OR sourcing_event_id IS NOT NULL
    display_name: Managed Flag
    synonyms:
      - managed spend indicator
  - name: managed_status
    expr: |-
      CASE WHEN contract_id IS NOT NULL AND sourcing_event_id IS NOT NULL THEN 'Contracted & Sourced'
           WHEN contract_id IS NOT NULL THEN 'Contracted only'
           WHEN sourcing_event_id IS NOT NULL THEN 'Sourced only'
           ELSE 'Unmanaged' END
    comment: "Sourcing-management quadrant from document lineage: both, contract-only,\
      \ sourced-only, or unmanaged tail."
    display_name: Managed Status
    synonyms:
      - management status
  - name: supplier_id
    expr: supplier_id
    display_name: Supplier Id
  - name: supplier_name
    expr: supplier_name
    display_name: Supplier Name
    synonyms:
      - supplier
      - vendor
  - name: supplier_region
    expr: supplier_region
    display_name: Supplier Region
    synonyms:
      - region
  - name: supplier_category
    expr: supplier_category
    comment: Supplier master primary category (carried on fact_invoices from dim_supplier).
    display_name: Supplier Category
    synonyms:
      - supplier primary category
  - name: payment_terms
    expr: payment_terms
    comment: Invoice payment terms (Net15/30/45/60).
    display_name: Payment Terms
    synonyms:
      - terms
      - net terms
  - name: is_regulated
    expr: is_regulated_supplier
    comment: "Regulated supplier (utilities, govt fees, single-source) — not sourcing's\
      \ to move."
    display_name: Is Regulated
    synonyms:
      - regulated
  - name: contract_id
    expr: contract_id
    display_name: Contract ID

measures:
  - name: total_spend
    expr: SUM(CASE WHEN payment_status = 'PAID' THEN amount ELSE 0 END)
    comment: Realized (paid) invoice-line spend.
    display_name: Total Spend
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 0
      abbreviation: compact
    synonyms:
      - spend
      - paid spend
      - total paid spend
  - name: addressable_spend
    expr: SUM(CASE WHEN payment_status = 'PAID' AND addressability = 'Addressable'
      THEN amount ELSE 0 END)
    comment: Paid spend with a non-regulated supplier (sourcing can act on it).
    display_name: Addressable Spend
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 0
      abbreviation: compact
    synonyms:
      - sourceable spend
  - name: managed_spend
    expr: SUM(CASE WHEN payment_status = 'PAID' AND addressability = 'Addressable'
      AND (contract_id IS NOT NULL OR sourcing_event_id IS NOT NULL) THEN amount ELSE
      0 END)
    comment: "Addressable paid spend under sourcing management (active contract OR\
      \ competitively sourced), in dollars."
    display_name: Managed Spend
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 0
      abbreviation: compact
    synonyms:
      - spend under management
      - managed dollars
  - name: unmanaged_spend
    expr: SUM(CASE WHEN payment_status = 'PAID' AND addressability = 'Addressable'
      AND NOT (contract_id IS NOT NULL OR sourcing_event_id IS NOT NULL) THEN amount
      ELSE 0 END)
    comment: "Addressable paid spend NOT under management (off-contract and not sourced)\
      \ — the sourcing opportunity / tail, in dollars."
    display_name: Unmanaged Spend
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 0
      abbreviation: compact
    synonyms:
      - off-contract dollars
      - tail spend dollars
      - leakage
  - name: managed_spend_pct
    expr: "SUM(CASE WHEN payment_status = 'PAID' AND addressability = 'Addressable'\
      \ AND (contract_id IS NOT NULL OR sourcing_event_id IS NOT NULL) THEN amount\
      \ ELSE 0 END) / NULLIF(SUM(CASE WHEN payment_status = 'PAID' AND addressability\
      \ = 'Addressable' THEN amount ELSE 0 END), 0)"
    comment: "Share of addressable paid spend under sourcing management (active contract\
      \ OR competitively sourced), by dollars. Excludes PO-match."
    display_name: Managed Spend Pct
    format:
      type: percentage
      decimal_places:
        type: max
        places: 1
    synonyms:
      - spend under management
      - managed spend ratio
  - name: managed_spend_pct_count
    expr: "SUM(CASE WHEN payment_status = 'PAID' AND addressability = 'Addressable'\
      \ AND (contract_id IS NOT NULL OR sourcing_event_id IS NOT NULL) THEN 1 ELSE\
      \ 0 END) / NULLIF(SUM(CASE WHEN payment_status = 'PAID' AND addressability =\
      \ 'Addressable' THEN 1 ELSE 0 END), 0)"
    comment: Managed share by invoice-line COUNT (not dollars). Lower than the dollar
      share — managed spend concentrates in a few large buys.
    display_name: Managed Spend Pct (count)
    format:
      type: percentage
      decimal_places:
        type: max
        places: 1
    synonyms:
      - managed by count
      - managed line share
  - name: contract_coverage_pct
    expr: "SUM(CASE WHEN payment_status = 'PAID' AND addressability = 'Addressable'\
      \ AND contract_id IS NOT NULL THEN amount ELSE 0 END) / NULLIF(SUM(CASE WHEN\
      \ payment_status = 'PAID' AND addressability = 'Addressable' THEN amount ELSE\
      \ 0 END), 0)"
    comment: Share of addressable paid spend on a line linked to a contract (by dollars).
    display_name: Contract Coverage Pct
    format:
      type: percentage
      decimal_places:
        type: max
        places: 1
    synonyms:
      - contracted spend ratio
      - contract penetration
  - name: contract_coverage_pct_count
    expr: "SUM(CASE WHEN payment_status = 'PAID' AND addressability = 'Addressable'\
      \ AND contract_id IS NOT NULL THEN 1 ELSE 0 END) / NULLIF(SUM(CASE WHEN payment_status\
      \ = 'PAID' AND addressability = 'Addressable' THEN 1 ELSE 0 END), 0)"
    comment: Contract coverage by invoice-line COUNT — markedly lower than the dollar
      share.
    display_name: Contract Coverage Pct (count)
    format:
      type: percentage
      decimal_places:
        type: max
        places: 1
    synonyms:
      - contract coverage by count
  - name: sourced_pct
    expr: "SUM(CASE WHEN payment_status = 'PAID' AND addressability = 'Addressable'\
      \ AND sourcing_event_id IS NOT NULL THEN amount ELSE 0 END) / NULLIF(SUM(CASE\
      \ WHEN payment_status = 'PAID' AND addressability = 'Addressable' THEN amount\
      \ ELSE 0 END), 0)"
    comment: Share of addressable paid spend with a supplier won through a competitive
      sourcing event.
    display_name: Sourced Pct
    format:
      type: percentage
      decimal_places:
        type: max
        places: 1
    synonyms:
      - competitively sourced ratio
  - name: po_coverage_pct
    expr: "SUM(CASE WHEN payment_status = 'PAID' AND addressability = 'Addressable'\
      \ AND po_matched_flag = 'Y' THEN amount ELSE 0 END) / NULLIF(SUM(CASE WHEN payment_status\
      \ = 'PAID' AND addressability = 'Addressable' THEN amount ELSE 0 END), 0)"
    comment: 3-way-match / PO coverage — AP hygiene. NOT a spend-management metric.
    display_name: PO Coverage Pct
    format:
      type: percentage
      decimal_places:
        type: max
        places: 1
    synonyms:
      - po match rate
      - three way match rate
  - name: classified_spend_pct
    expr: "SUM(CASE WHEN payment_status = 'PAID' AND addressability = 'Addressable'\
      \ AND predicted_secondary_category IS NOT NULL THEN amount ELSE 0 END) / NULLIF(SUM(CASE\
      \ WHEN payment_status = 'PAID' AND addressability = 'Addressable' THEN amount\
      \ ELSE 0 END), 0)"
    comment: Share of addressable paid spend with an ML-predicted category. NULL until
      the classification job runs.
    display_name: Classified Spend Pct
    format:
      type: percentage
      decimal_places:
        type: max
        places: 1
    synonyms:
      - ml coverage
      - classification coverage
  - name: on_time_payment_pct
    expr: "SUM(CASE WHEN payment_status = 'PAID' AND is_on_time_payment THEN amount\
      \ ELSE 0 END) / NULLIF(SUM(CASE WHEN payment_status = 'PAID' THEN amount ELSE\
      \ 0 END), 0)"
    comment: Spend-weighted share of paid spend settled on or before the due date.
    display_name: On-Time Payment Pct
    format:
      type: percentage
      decimal_places:
        type: max
        places: 1
    synonyms:
      - otp
      - on time payment rate
  - name: invoice_count
    expr: SUM(CASE WHEN payment_status = 'PAID' THEN 1 ELSE 0 END)
    comment: Count of paid invoice lines.
    display_name: Invoice Count
    format:
      type: number
      decimal_places:
        type: exact
        places: 0
    synonyms:
      - invoices
      - line count
  - name: avg_dpo
    expr: AVG(CASE WHEN payment_status = 'PAID' THEN days_to_pay END)
    comment: Average days payable outstanding across paid lines.
    display_name: Avg DPO
    format:
      type: number
      decimal_places:
        type: max
        places: 1
    synonyms:
      - days payable outstanding
      - payment days
  - name: measured_maverick_pct
    expr: "SUM(CASE WHEN payment_status = 'PAID' AND NOT (contract_id IS NOT NULL\
      \ OR sourcing_event_id IS NOT NULL) THEN amount ELSE 0 END) / NULLIF(SUM(CASE\
      \ WHEN payment_status = 'PAID' THEN amount ELSE 0 END), 0)"
    comment: Share of paid spend NOT under management (off-contract and not sourced)
      — observed maverick/tail spend.
    display_name: Measured Maverick Pct
    format:
      type: percentage
      decimal_places:
        type: max
        places: 1
    synonyms:
      - maverick spend ratio
      - off-contract spend
      - tail spend
  - name: active_supplier_count
    expr: COUNT(DISTINCT contract_id)
    display_name: Active Supplier Count
    format:
      type: number
      decimal_places:
        type: exact
        places: 0
    synonyms:
      - active suppliers
$$
"""

# ── Nested: gold.mv_supplier_performance (source = gold.mv_spend) ─────────────
mv_supplier_performance = f"""
CREATE OR REPLACE VIEW {fq_gold}.mv_supplier_performance
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "Parties subject view — supplier performance. Nested on mv_spend so all flag/measure logic is inherited (no duplication). Filter Invoice Date >= date_sub(current_date,365) for the trailing-12-month scorecard."
source: {catalog}.{gold}.mv_spend
dimensions:
  - name: supplier_id
    display_name: "Supplier Id"
    expr: supplier_id
  - name: supplier_name
    display_name: "Supplier Name"
    expr: supplier_name
    synonyms: ['supplier', 'vendor']
  - name: supplier_region
    display_name: "Supplier Region"
    expr: supplier_region
    synonyms: ['region']
  - name: supplier_category
    display_name: "Supplier Category"
    expr: supplier_category
    synonyms: ['category']
  - name: payment_terms
    display_name: "Payment Terms"
    expr: payment_terms
    synonyms: ['terms']
  - name: is_regulated
    display_name: "Is Regulated"
    expr: is_regulated
    synonyms: ['regulated']
  - name: invoice_date
    display_name: "Invoice Date"
    expr: invoice_date
  - name: fiscal_year
    display_name: "Fiscal Year"
    expr: fiscal_year
  - name: fiscal_quarter
    display_name: "Fiscal Quarter"
    expr: fiscal_quarter
measures:
  - name: trailing_spend
    display_name: "Trailing Spend"
    expr: MEASURE(total_spend)
    comment: "Paid spend with the supplier (filter invoice_date to trailing-12-month for the scorecard)."
    synonyms: ['supplier spend', 'spend']
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 0
      abbreviation: compact
  - name: managed_spend
    display_name: "Managed Spend"
    expr: MEASURE(managed_spend)
    comment: "This supplier's addressable paid spend under management (contract or sourced), in dollars."
    synonyms: ['managed dollars']
    format:
      type: currency
      currency_code: USD
      decimal_places:
        type: exact
        places: 0
      abbreviation: compact
  - name: managed_spend_pct
    display_name: "Managed Spend Pct"
    expr: MEASURE(managed_spend_pct)
    comment: "Share of this supplier's addressable paid spend under management."
    synonyms: ['managed spend ratio']
    format:
      type: percentage
      decimal_places:
        type: max
        places: 1
  - name: invoice_count
    display_name: "Invoice Count"
    expr: MEASURE(invoice_count)
    synonyms: ['invoices']
    format:
      type: number
      decimal_places:
        type: exact
        places: 0
  - name: on_time_payment_pct
    display_name: "On-Time Payment Pct"
    expr: MEASURE(on_time_payment_pct)
    comment: "Spend-weighted on-time payment share for this supplier."
    synonyms: ['otp', 'on time payment rate']
    format:
      type: percentage
      decimal_places:
        type: max
        places: 1
  - name: avg_dpo
    display_name: "Avg DPO"
    expr: MEASURE(avg_dpo)
    synonyms: ['days payable outstanding']
    format:
      type: number
      decimal_places:
        type: max
        places: 1
  - name: measured_maverick_pct
    display_name: "Measured Maverick Pct"
    expr: MEASURE(measured_maverick_pct)
    comment: "Share of this supplier's paid spend not under management (off-contract and not sourced)."
    synonyms: ['maverick spend ratio', 'off-contract spend']
    format:
      type: percentage
      decimal_places:
        type: max
        places: 1
$$
"""

print(f"Applying metric views to {catalog}.{gold} ...")
spark.sql(mv_spend)
print(f"  ✓ {catalog}.{gold}.mv_spend")
spark.sql(mv_supplier_performance)
print(f"  ✓ {catalog}.{gold}.mv_supplier_performance (nested on mv_spend)")

# ── Validation — fail the task if the headline KPIs don't compute ────────────
# Ratio measures are stored as fractions; multiply by 100 here purely for a
# human-readable log line.
kpi = spark.sql(f"""
    SELECT
      ROUND(MEASURE(total_spend)/1e9, 2)                AS total_spend_b,
      ROUND(MEASURE(managed_spend_pct) * 100, 1)        AS managed_pct,
      ROUND(MEASURE(managed_spend_pct_count) * 100, 1)  AS managed_count_pct,
      ROUND(MEASURE(contract_coverage_pct) * 100, 1)    AS contract_pct,
      ROUND(MEASURE(sourced_pct) * 100, 1)              AS sourced_pct,
      ROUND(MEASURE(po_coverage_pct) * 100, 1)          AS po_coverage_pct,
      ROUND(MEASURE(on_time_payment_pct) * 100, 1)      AS on_time_pct
    FROM {catalog}.{gold}.mv_spend
    WHERE invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
""").collect()[0]
print(f"  T12M KPIs → total=${kpi['total_spend_b']}B "
      f"managed={kpi['managed_pct']}% (by count {kpi['managed_count_pct']}%) "
      f"contract={kpi['contract_pct']}% sourced={kpi['sourced_pct']}% "
      f"po_cov={kpi['po_coverage_pct']}% on_time={kpi['on_time_pct']}%")
assert kpi["managed_pct"] is not None, "Managed Spend Pct returned NULL — check source data is loaded"
print("Metric views applied and validated.")
