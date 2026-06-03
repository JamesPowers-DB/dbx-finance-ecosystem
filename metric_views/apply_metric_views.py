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

dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema", "finance_spend_analytics")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")

# Single schema; tables are layer-prefixed (gold_ / silver_). Metric views are
# gold-layer consumption artifacts, so they're created as gold_mv_*.
fq = f"`{catalog}`.`{schema}`"

# ── Base: gold.mv_spend ──────────────────────────────────────────────────────
# Straight table source over gold.fact_invoices — the per-line conditions live
# inline in the measure expressions. Catalog/schema are interpolated so the same
# definition deploys to dev and prod unchanged.
mv_spend = f"""
CREATE OR REPLACE VIEW {fq}.gold_mv_spend
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1

source: {catalog}.{schema}.gold_fact_invoices

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
  - name: active_periods
    expr: COUNT(DISTINCT fiscal_year * 10 + fiscal_quarter)
    comment: "Distinct fiscal quarters with activity — consistency signal feeding the supplier reliability score."
    display_name: Active Periods
    format:
      type: number
      decimal_places:
        type: exact
        places: 0
    synonyms:
      - active quarters
$$
"""

# ── Nested: gold.mv_supplier_performance (source = gold.mv_spend) ─────────────
mv_supplier_performance = f"""
CREATE OR REPLACE VIEW {fq}.gold_mv_supplier_performance
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "Parties subject view — supplier performance. Nested on mv_spend so all flag/measure logic is inherited (no duplication). Filter Invoice Date >= date_sub(current_date,365) for the trailing-12-month scorecard."
source: {catalog}.{schema}.gold_mv_spend
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
  - name: governed_spend_pct
    display_name: "Governed Spend Pct"
    expr: 1 - MEASURE(measured_maverick_pct)
    comment: "Share of this supplier's paid spend that IS under management (the complement of maverick) — always has a denominator, including regulated suppliers."
    synonyms: ['managed share', 'under-management share']
    format:
      type: percentage
      decimal_places:
        type: max
        places: 1
  - name: active_periods
    display_name: "Active Periods"
    expr: MEASURE(active_periods)
    comment: "Distinct fiscal quarters this supplier was active — relationship consistency."
    synonyms: ['active quarters', 'tenure']
    format:
      type: number
      decimal_places:
        type: exact
        places: 0
  - name: reliability_score
    display_name: "Reliability Score"
    expr: "0.5 * (1 - MEASURE(measured_maverick_pct)) + 0.3 * COALESCE(MEASURE(managed_spend_pct), 0) + 0.2 * LEAST(MEASURE(active_periods) / 8.0, 1)"
    comment: "Governance-based supplier reliability index (0-1). NO delivery/quality ground truth exists in the data, so 'reliability' is defined as how controlled and consistent the relationship is: 0.5 x governed share (1 - maverick) + 0.3 x managed coverage of addressable spend + 0.2 x consistency (active quarters / 8, capped). Rank suppliers by this for 'most reliable suppliers'. Filter to a minimum trailing spend to ignore one-off vendors."
    synonyms: ['reliability', 'most reliable', 'supplier reliability', 'reliability index']
    format:
      type: number
      decimal_places:
        type: max
        places: 3
$$
"""

# ── Subject view: gold.mv_contracts (buy-side contract portfolio) ─────────────
# Source = silver.contract_inbound (Ariba contract workspaces). contract_workspace_id
# is the contract_id stamped on PR/PO/invoice lines, so this ties to mv_spend /
# mv_purchase_orders. Utilization is dollar-weighted (actual / committed) — a
# count-based "% utilized" is ~100% because every contract carries some spend.
# Token-replaced (not f-string) so the inline-brace YAML flow-mappings survive.
_MV_CONTRACTS_SQL = '''CREATE OR REPLACE VIEW __CAT__.__GOLD__.mv_contracts
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: __CAT__.__SILVER__.contract_inbound
comment: "Buy-side (procurement) contract portfolio from Ariba contract workspaces. One row per inbound contract. Utilization = actual_spend_to_date / total_committed_spend (dollar-weighted). contract_workspace_id is the contract_id stamped on PR/PO/invoice lines (links to mv_spend / mv_purchase_orders). Sell-side customer contracts are NOT here (revenue subject)."
joins:
  - name: supplier
    source: __CAT__.__GOLD__.dim_supplier
    on: source.supplier_id = supplier.supplier_id
dimensions:
  - name: contract_workspace_id
    expr: contract_workspace_id
    display_name: Contract ID
    synonyms: ['contract id', 'contract', 'workspace id']
  - name: contract_type
    expr: contract_type
    display_name: Contract Type
  - name: status
    expr: status
    display_name: Status
    synonyms: ['contract status']
  - name: region
    expr: region
    display_name: Region
    synonyms: ['owning region']
  - name: supplier_id
    expr: supplier_id
    display_name: Supplier Id
  - name: supplier_name
    expr: supplier.supplier_name
    display_name: Supplier Name
    synonyms: ['supplier', 'vendor', 'counterparty']
  - name: effective_date
    expr: effective_date
    display_name: Effective Date
  - name: expiration_date
    expr: expiration_date
    display_name: Expiration Date
  - name: is_active
    expr: (status = 'Active' AND current_date() BETWEEN effective_date AND expiration_date)
    display_name: Is Active
  - name: is_expiring_90d
    expr: (expiration_date BETWEEN current_date() AND date_add(current_date(), 90))
    display_name: Expiring In 90 Days
measures:
  - name: contract_count
    expr: COUNT(DISTINCT contract_workspace_id)
    display_name: Contract Count
    synonyms: ['contracts', 'number of contracts']
    format:
      type: number
      decimal_places: {type: exact, places: 0}
  - name: total_committed
    expr: SUM(total_committed_spend)
    display_name: Total Committed
    synonyms: ['committed spend', 'contract value', 'ceiling']
    format: {type: currency, currency_code: USD, decimal_places: {type: exact, places: 0}, abbreviation: compact}
  - name: total_actual
    expr: SUM(actual_spend_to_date)
    display_name: Total Actual Spend
    synonyms: ['actual spend', 'spend to date']
    format: {type: currency, currency_code: USD, decimal_places: {type: exact, places: 0}, abbreviation: compact}
  - name: utilization_rate
    expr: SUM(actual_spend_to_date) / NULLIF(SUM(total_committed_spend), 0)
    comment: "Dollar-weighted contract utilization: actual spend to date / total committed. This is the answer to 'what percent of contracts have been utilized'."
    display_name: Utilization Rate
    synonyms: ['contract utilization', 'percent utilized', 'contracts utilized', 'usage rate']
    format: {type: percentage, decimal_places: {type: max, places: 1}}
  - name: remaining_commitment
    expr: SUM(total_committed_spend - actual_spend_to_date)
    display_name: Remaining Commitment
    synonyms: ['headroom', 'unused commitment']
    format: {type: currency, currency_code: USD, decimal_places: {type: exact, places: 0}, abbreviation: compact}
  - name: avg_contract_value
    expr: AVG(total_committed_spend)
    display_name: Avg Contract Value
    format: {type: currency, currency_code: USD, decimal_places: {type: exact, places: 0}, abbreviation: compact}
  - name: expiring_90d_count
    expr: SUM(CASE WHEN expiration_date BETWEEN current_date() AND date_add(current_date(), 90) THEN 1 ELSE 0 END)
    display_name: Expiring In 90 Days
    synonyms: ['expiring soon', 'renewals due']
    format: {type: number, decimal_places: {type: exact, places: 0}}
  - name: over_utilized_count
    expr: SUM(CASE WHEN actual_spend_to_date > total_committed_spend THEN 1 ELSE 0 END)
    comment: "Contracts spent past their committed ceiling — overspend / off-ceiling leakage risk."
    display_name: Over-Utilized Count
    format: {type: number, decimal_places: {type: exact, places: 0}}
$$'''
mv_contracts = (_MV_CONTRACTS_SQL
                .replace("__CAT__.__GOLD__.", f"{catalog}.{schema}.gold_")
                .replace("__CAT__.__SILVER__.", f"{catalog}.{schema}.silver_"))

# ── Subject view: gold.mv_purchase_orders (request -> order step) ──────────────
# PO line grain LEFT JOINed to the originating PR (fact_purchase_requests) so
# requisition context rides on every PO line. PR->PO cycle time is omitted (PR and
# PO are stamped same-day in the source). Headline story is off-contract PO leakage
# by requisition source channel.
_MV_PURCHASE_ORDERS_SQL = '''CREATE OR REPLACE VIEW __CAT__.__GOLD__.mv_purchase_orders
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: __CAT__.__GOLD__.fact_purchase_orders
comment: "Purchase-order commitment fact (PO line grain) LEFT JOINed to the originating purchase request (fact_purchase_requests on source_pr_number + source_pr_line_num) so requisition context rides on every PO line. Covers the request-to-order step of the spend lifecycle: PO commitment dollars, PR->PO conversion, source-channel mix, and off-contract PO leakage. Managed = PO line carries a contract_id or sourcing_event_id."
joins:
  - name: pr
    source: __CAT__.__GOLD__.fact_purchase_requests
    on: source.source_pr_number = pr.pr_number AND source.source_pr_line_num = pr.pr_line_num
dimensions:
  - name: po_status
    expr: po_status
    display_name: PO Status
  - name: po_doc_type
    expr: po_doc_type
    display_name: PO Doc Type
  - name: segment
    expr: segment_code
    display_name: Segment
    synonyms: ['business segment', 'division']
  - name: supplier_id
    expr: supplier_id
    display_name: Supplier Id
  - name: supplier_name
    expr: supplier_name
    display_name: Supplier Name
    synonyms: ['supplier', 'vendor']
  - name: supplier_region
    expr: supplier_region
    display_name: Supplier Region
    synonyms: ['region']
  - name: pr_source
    expr: pr_source
    comment: "Origination channel of the requisition (Catalog / AribaPortal / ManualSubmission / ProcurementAgent)."
    display_name: PR Source
    synonyms: ['origination channel', 'requisition source', 'purchase channel']
  - name: category_primary
    expr: true_category_primary
    display_name: Category Primary
    synonyms: ['spend category', 'category']
  - name: category_secondary
    expr: true_category_secondary
    display_name: Category Secondary
  - name: fiscal_year
    expr: fiscal_year
    display_name: Fiscal Year
    synonyms: ['fy', 'year']
  - name: fiscal_quarter
    expr: fiscal_quarter
    display_name: Fiscal Quarter
    synonyms: ['fq', 'quarter']
  - name: po_created_date
    expr: po_created_date
    display_name: PO Created Date
  - name: managed_status
    expr: |-
      CASE WHEN contract_id IS NOT NULL AND sourcing_event_id IS NOT NULL THEN 'Contracted & Sourced'
           WHEN contract_id IS NOT NULL THEN 'Contracted only'
           WHEN sourcing_event_id IS NOT NULL THEN 'Sourced only'
           ELSE 'Off-contract' END
    display_name: Managed Status
  - name: pr_status
    expr: pr.pr_status
    display_name: PR Status
  - name: requester_id
    expr: pr.requester_id
    display_name: Requester Id
  - name: pr_doc_type
    expr: pr.pr_doc_type
    display_name: PR Doc Type
measures:
  - name: po_line_count
    expr: COUNT(*)
    display_name: PO Line Count
    format: {type: number, decimal_places: {type: exact, places: 0}}
  - name: po_count
    expr: COUNT(DISTINCT po_number)
    display_name: PO Count
    synonyms: ['purchase orders', 'number of pos']
    format: {type: number, decimal_places: {type: exact, places: 0}}
  - name: total_po_amount
    expr: SUM(extended_amount)
    display_name: Total PO Amount
    synonyms: ['po spend', 'committed po value', 'order value']
    format: {type: currency, currency_code: USD, decimal_places: {type: exact, places: 0}, abbreviation: compact}
  - name: off_contract_po_amount
    expr: SUM(CASE WHEN contract_id IS NULL AND sourcing_event_id IS NULL THEN extended_amount ELSE 0 END)
    comment: "PO dollars with no contract and no sourcing event — request-to-order leakage."
    display_name: Off-Contract PO Amount
    synonyms: ['off contract po spend', 'po leakage']
    format: {type: currency, currency_code: USD, decimal_places: {type: exact, places: 0}, abbreviation: compact}
  - name: off_contract_po_pct
    expr: SUM(CASE WHEN contract_id IS NULL AND sourcing_event_id IS NULL THEN extended_amount ELSE 0 END) / NULLIF(SUM(extended_amount), 0)
    display_name: Off-Contract PO Pct
    synonyms: ['po leakage rate', 'off contract share']
    format: {type: percentage, decimal_places: {type: max, places: 1}}
  - name: managed_po_pct
    expr: SUM(CASE WHEN contract_id IS NOT NULL OR sourcing_event_id IS NOT NULL THEN extended_amount ELSE 0 END) / NULLIF(SUM(extended_amount), 0)
    comment: "Share of PO dollars on a contract or sourcing event."
    display_name: Managed PO Pct
    format: {type: percentage, decimal_places: {type: max, places: 1}}
  - name: prs_converted
    expr: COUNT(DISTINCT source_pr_number)
    comment: "Distinct purchase requests that resulted in a PO."
    display_name: PRs Converted
    synonyms: ['requisitions converted', 'prs ordered']
    format: {type: number, decimal_places: {type: exact, places: 0}}
  - name: total_pr_estimate
    expr: SUM(pr.estimated_extended_amount)
    comment: "Summed requisition estimate for the joined PR lines (compare to total_po_amount for estimate accuracy)."
    display_name: Total PR Estimate
    format: {type: currency, currency_code: USD, decimal_places: {type: exact, places: 0}, abbreviation: compact}
  - name: avg_po_line_value
    expr: AVG(extended_amount)
    display_name: Avg PO Line Value
    format: {type: currency, currency_code: USD, decimal_places: {type: exact, places: 0}, abbreviation: compact}
$$'''
mv_purchase_orders = (_MV_PURCHASE_ORDERS_SQL
                      .replace("__CAT__.__GOLD__.", f"{catalog}.{schema}.gold_"))

# ── Subject view: gold.mv_cost_savings (low priority) ─────────────────────────
# Auto-detected sourcing savings (baseline back-calculated from event type).
_MV_COST_SAVINGS_SQL = '''CREATE OR REPLACE VIEW __CAT__.__GOLD__.mv_cost_savings
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
source: __CAT__.__GOLD__.fact_cost_savings
comment: "Auto-detected procurement cost reductions from closed/awarded sourcing events. Savings = baseline_amount - awarded_amount, where the pre-negotiation baseline is back-calculated from the event type (Auction ~25%, RFP ~18%, RFQ ~12%). Manual cost-avoidance entries live in Lakebase and are NOT in this view. Low-priority subject."
dimensions:
  - name: event_type
    expr: event_type
    display_name: Event Type
    synonyms: ['sourcing event type', 'rfx type']
  - name: segment
    expr: segment_code
    display_name: Segment
    synonyms: ['business segment', 'division']
  - name: category_primary
    expr: category_primary
    display_name: Category Primary
    synonyms: ['spend category', 'category']
  - name: supplier_id
    expr: supplier_id
    display_name: Supplier Id
  - name: supplier_name
    expr: supplier_name
    display_name: Supplier Name
    synonyms: ['supplier', 'vendor']
  - name: owner_org_unit
    expr: owner_org_unit
    display_name: Owner Org Unit
    synonyms: ['sourcing team', 'org unit']
  - name: savings_type
    expr: savings_type
    display_name: Savings Type
  - name: fiscal_year
    expr: fiscal_year
    display_name: Fiscal Year
    synonyms: ['fy', 'year']
  - name: fiscal_quarter
    expr: fiscal_quarter
    display_name: Fiscal Quarter
    synonyms: ['fq', 'quarter']
measures:
  - name: total_savings
    expr: SUM(savings_amount_usd)
    display_name: Total Savings
    synonyms: ['savings', 'cost savings', 'cost reduction', 'realized savings']
    format: {type: currency, currency_code: USD, decimal_places: {type: exact, places: 0}, abbreviation: compact}
  - name: total_awarded
    expr: SUM(awarded_amount)
    display_name: Total Awarded
    synonyms: ['awarded spend', 'awarded amount']
    format: {type: currency, currency_code: USD, decimal_places: {type: exact, places: 0}, abbreviation: compact}
  - name: total_baseline
    expr: SUM(baseline_amount)
    display_name: Total Baseline
    synonyms: ['baseline spend', 'pre-negotiation']
    format: {type: currency, currency_code: USD, decimal_places: {type: exact, places: 0}, abbreviation: compact}
  - name: effective_savings_rate
    expr: SUM(savings_amount_usd) / NULLIF(SUM(baseline_amount), 0)
    comment: "Dollar-weighted savings rate = savings / baseline."
    display_name: Effective Savings Rate
    synonyms: ['savings rate', 'savings percent']
    format: {type: percentage, decimal_places: {type: max, places: 1}}
  - name: event_count
    expr: COUNT(DISTINCT savings_event_id)
    display_name: Event Count
    synonyms: ['sourcing events', 'number of events']
    format: {type: number, decimal_places: {type: exact, places: 0}}
$$'''
mv_cost_savings = (_MV_COST_SAVINGS_SQL
                   .replace("__CAT__.__GOLD__.", f"{catalog}.{schema}.gold_"))

print(f"Applying metric views to {catalog}.{schema} ...")
spark.sql(mv_spend)
print(f"  ✓ {catalog}.{schema}.gold_mv_spend")
spark.sql(mv_supplier_performance)
print(f"  ✓ {catalog}.{schema}.gold_mv_supplier_performance (nested on gold_mv_spend)")
spark.sql(mv_contracts)
print(f"  ✓ {catalog}.{schema}.gold_mv_contracts")
spark.sql(mv_purchase_orders)
print(f"  ✓ {catalog}.{schema}.gold_mv_purchase_orders (PO line grain + PR join)")
spark.sql(mv_cost_savings)
print(f"  ✓ {catalog}.{schema}.gold_mv_cost_savings")

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
    FROM {catalog}.{schema}.gold_mv_spend
    WHERE invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
""").collect()[0]
print(f"  T12M KPIs → total=${kpi['total_spend_b']}B "
      f"managed={kpi['managed_pct']}% (by count {kpi['managed_count_pct']}%) "
      f"contract={kpi['contract_pct']}% sourced={kpi['sourced_pct']}% "
      f"po_cov={kpi['po_coverage_pct']}% on_time={kpi['on_time_pct']}%")
assert kpi["managed_pct"] is not None, "Managed Spend Pct returned NULL — check source data is loaded"
print("Metric views applied and validated.")
