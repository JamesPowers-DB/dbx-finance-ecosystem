"""Shared definition of the Strategic Spend Analytics Genie space.

Pure-Python (no Databricks/CLI deps) so it can be imported by BOTH:
  - genie/provision_genie_space.py        (local CLI, ad-hoc)
  - genie/provision_genie_space_job.py    (in-bundle job task, the canonical path)

It builds the version-2 ``serialized_space`` (metric-view-only data sources,
instructions, curated example SQL, benchmarks, sample questions) for a given
catalog/gold-schema, and defines the canonical per-target space title that the
app resolves by name at runtime.
"""

from __future__ import annotations

import itertools

DEFAULT_DESCRIPTION = (
    "End-to-end spend visibility across the procurement lifecycle "
    "(source/contract -> request -> order -> invoice -> paid). Ask about "
    "spend, suppliers, contracts, purchase orders, and sourcing savings. "
    "Answers are computed only from governed UC metric views."
)

# Canonical title convention. The app derives <target> from its own app name and
# resolves the space id by this exact title — so nothing has to write an id back
# into app.yaml. Keep this in lockstep with the app's resolver.
TITLE_BASE = "Strategic Spend Analytics"


def space_title(target: str) -> str:
    return f"{TITLE_BASE} ({target})"


# Genie validates that every id-keyed collection is sorted by id. Monotonic
# 32-char-hex ids assigned in insertion order satisfy that while preserving the
# authored display order.
_ID_COUNTER = itertools.count(1)


def _next_id() -> str:
    return f"{next(_ID_COUNTER):032x}"


def _lines(text: str) -> list[str]:
    return text.splitlines(keepends=True) or [text]


def build_serialized_space(catalog: str, schema_gold: str) -> dict:
    """Build the version-2 serialized_space for the given target.

    Every curated object is a metric view in ``catalog.schema_gold``; every
    example/benchmark query uses MEASURE() against those views.
    """
    fq = f"{catalog}.{schema_gold}"
    mv_spend = f"{fq}.mv_spend"
    mv_supplier = f"{fq}.mv_supplier_performance"
    mv_contracts = f"{fq}.mv_contracts"
    mv_pos = f"{fq}.mv_purchase_orders"
    mv_savings = f"{fq}.mv_cost_savings"

    tables = sorted(
        [{"identifier": i} for i in (mv_spend, mv_supplier, mv_contracts, mv_pos, mv_savings)],
        key=lambda t: t["identifier"],
    )

    sample_questions = [
        "Who are my top 5 vendors by spend?",
        "What percent of our contracts have been utilized?",
        "Who do we have the best payment terms with for IT & Telecom spend?",
        "Who are our most reliable suppliers?",
        "What share of our spend is managed vs maverick?",
        "Which purchase request channels leak the most off-contract spend?",
    ]

    instructions_text = (
        "## What this space answers\n"
        "Strategic Spend Analytics gives end-to-end visibility into the procurement "
        "spend lifecycle: source/contract -> request -> order -> invoice -> paid. "
        "Topics: realized spend, suppliers/vendors, buy-side contracts, purchase "
        "orders & requisitions, and sourcing cost savings.\n\n"
        "## HARD RULE: metric views only\n"
        "Only query the five curated UC metric views, and ALWAYS wrap aggregates in "
        "the MEASURE() function. GROUP BY dimensions directly; never SUM/COUNT a raw "
        "column and never query raw fact_/dim_ tables. The metric views already "
        "encode the governed conditions (PAID, addressable, managed) so numbers match "
        "the app's KPIs.\n\n"
        "## Which view to use\n"
        f"- `{mv_spend}` — realized (PAID) AP invoice spend. Use for total/addressable/"
        "managed spend, spend by category, segment, supplier, region, payment terms, "
        "PR source, DPO and on-time payment, and 'top vendors'. Key measures: "
        "total_spend, managed_spend, managed_spend_pct, contract_coverage_pct, "
        "sourced_pct, measured_maverick_pct, on_time_payment_pct, avg_dpo.\n"
        f"- `{mv_supplier}` — per-supplier scorecard (nested on mv_spend). Use for "
        "'most reliable suppliers' (reliability_score), governed_spend_pct, "
        "trailing_spend, on_time_payment_pct, avg_dpo.\n"
        f"- `{mv_contracts}` — buy-side (procurement) contract portfolio. Use for "
        "'what % of contracts have been utilized' (utilization_rate), committed vs "
        "actual spend, expiring contracts (expiring_90d_count), and contracts by "
        "supplier/type/region.\n"
        f"- `{mv_pos}` — purchase-order commitments joined to their originating "
        "purchase request. Use for PO value, off-contract PO leakage "
        "(off_contract_po_pct), spend by PR source channel, and PRs converted.\n"
        f"- `{mv_savings}` — auto-detected sourcing-event cost savings (lower priority). "
        "Use for total_savings, effective_savings_rate by event type/segment/supplier.\n\n"
        "## Definitions & benchmarks\n"
        "- SPEND means realized PAID invoice spend; total_spend already filters to PAID. "
        "Trailing-12-month total is ~$2.96B and ~50.6% is managed.\n"
        "- MANAGED SPEND = addressable spend under an active contract OR a competitive "
        "sourcing event (NOT PO-match). The complement is maverick/tail spend.\n"
        "- MOST RELIABLE SUPPLIERS: there is NO delivery/quality data, so reliability is "
        "a GOVERNANCE index. Use mv_supplier_performance.reliability_score (0-1, higher = "
        "better: governed share + managed coverage + multi-quarter consistency). Rank by "
        "MEASURE(reliability_score) DESC and filter HAVING MEASURE(trailing_spend) > "
        "1000000 so one-off vendors don't dominate.\n"
        "- '% OF CONTRACTS UTILIZED' = MEASURE(utilization_rate) on mv_contracts "
        "(dollar-weighted actual/committed, ~40.7%). Nearly every contract has some "
        "spend, so a count-based 'utilized' is ~100% and not meaningful — use the rate.\n"
        "- BEST PAYMENT TERMS = the LONGEST net terms (Net60 > Net45 > Net30 > Net15), "
        "which benefit our cash. payment_terms is a dimension on mv_spend.\n"
        "- TRAILING 12 MONTHS: filter invoice_date >= date_sub(current_date(), 365).\n"
        "- Segments are AD, PA, SB, ET, CORP. PR source channels are Catalog (cleanest), "
        "AribaPortal, ManualSubmission and ProcurementAgent (highest off-contract).\n\n"
        "## Cross-view linkage\n"
        "mv_contracts.contract_workspace_id is the SAME identifier as the contract_id on "
        "mv_spend and mv_purchase_orders. Each metric view is self-contained — answer a "
        "question from a SINGLE view; do not try to join two metric views in one query.\n\n"
        "## Style\n"
        "Always state the time window and any filter you applied. Currency is USD. "
        "Percentages from *_pct measures are fractions formatted as percentages."
    )
    text_instructions = [{"id": _next_id(), "content": _lines(instructions_text)}]

    example_question_sqls = [
        {
            "id": _next_id(),
            "question": ["Who are my top 5 vendors by spend?"],
            "sql": _lines(
                f"SELECT supplier_name, MEASURE(total_spend) AS total_spend\n"
                f"FROM {mv_spend}\n"
                f"WHERE invoice_date >= date_sub(current_date(), 365)\n"
                f"GROUP BY supplier_name\nORDER BY total_spend DESC\nLIMIT 5"),
            "usage_guidance": ["Top vendors = realized paid spend over the trailing 12 months."],
        },
        {
            "id": _next_id(),
            "question": ["What percent of our contracts have been utilized?"],
            "sql": _lines(
                f"SELECT MEASURE(utilization_rate) AS contract_utilization,\n"
                f"       MEASURE(total_committed) AS total_committed,\n"
                f"       MEASURE(total_actual)    AS total_actual\nFROM {mv_contracts}"),
            "usage_guidance": ["Dollar-weighted utilization (actual/committed). Optionally GROUP BY contract_type/region/supplier_name."],
        },
        {
            "id": _next_id(),
            "question": ["Who do we have the best payment terms with for a given category?"],
            "sql": _lines(
                f"SELECT supplier_name, payment_terms, MEASURE(total_spend) AS spend\n"
                f"FROM {mv_spend}\nWHERE category_primary = :category\n"
                f"  AND invoice_date >= date_sub(current_date(), 365)\n"
                f"GROUP BY supplier_name, payment_terms\nORDER BY payment_terms DESC, spend DESC\nLIMIT 20"),
            "parameters": [{"name": "category", "type_hint": "STRING",
                            "default_value": {"values": ["IT & Telecom"]}}],
            "usage_guidance": ["Best terms = longest net terms (Net60 best). Filter by category_primary."],
        },
        {
            "id": _next_id(),
            "question": ["Who are our most reliable suppliers?"],
            "sql": _lines(
                f"SELECT supplier_name,\n       MEASURE(reliability_score) AS reliability,\n"
                f"       MEASURE(governed_spend_pct) AS governed_pct,\n"
                f"       MEASURE(trailing_spend)     AS spend\nFROM {mv_supplier}\n"
                f"WHERE invoice_date >= date_sub(current_date(), 365)\nGROUP BY supplier_name\n"
                f"HAVING MEASURE(trailing_spend) > 1000000\nORDER BY reliability DESC\nLIMIT 10"),
            "usage_guidance": ["Reliability is a governance index (no delivery data exists). Filter to material suppliers."],
        },
        {
            "id": _next_id(),
            "question": ["Which purchase request channels leak the most off-contract spend?"],
            "sql": _lines(
                f"SELECT pr_source,\n       MEASURE(total_po_amount)     AS po_amount,\n"
                f"       MEASURE(off_contract_po_pct) AS off_contract_pct\nFROM {mv_pos}\n"
                f"GROUP BY pr_source\nORDER BY off_contract_pct DESC"),
            "usage_guidance": ["ManualSubmission and ProcurementAgent run the highest off-contract share."],
        },
        {
            "id": _next_id(),
            "question": ["How much have we saved through sourcing events by event type?"],
            "sql": _lines(
                f"SELECT event_type,\n       MEASURE(total_savings)          AS savings,\n"
                f"       MEASURE(effective_savings_rate) AS savings_rate\nFROM {mv_savings}\n"
                f"GROUP BY event_type\nORDER BY savings DESC"),
        },
    ]

    def _bench(q: str, sql: str) -> dict:
        return {"id": _next_id(), "question": [q],
                "answer": [{"format": "SQL", "content": _lines(sql)}]}

    benchmarks = [
        _bench("Who are my top 5 vendors?",
               f"SELECT supplier_name, MEASURE(total_spend) AS total_spend\nFROM {mv_spend}\n"
               f"WHERE invoice_date >= date_sub(current_date(), 365)\n"
               f"GROUP BY supplier_name ORDER BY total_spend DESC LIMIT 5"),
        _bench("What percent of contracts have been utilized?",
               f"SELECT MEASURE(utilization_rate) AS contract_utilization FROM {mv_contracts}"),
        _bench("Who are our most reliable suppliers?",
               f"SELECT supplier_name, MEASURE(reliability_score) AS reliability\nFROM {mv_supplier}\n"
               f"WHERE invoice_date >= date_sub(current_date(), 365)\n"
               f"GROUP BY supplier_name HAVING MEASURE(trailing_spend) > 1000000\n"
               f"ORDER BY reliability DESC LIMIT 10"),
        _bench("What is our managed vs maverick spend?",
               f"SELECT MEASURE(managed_spend_pct) AS managed_pct,\n"
               f"       MEASURE(measured_maverick_pct) AS maverick_pct\nFROM {mv_spend}\n"
               f"WHERE invoice_date >= date_sub(current_date(), 365)"),
    ]

    return {
        "version": 2,
        "config": {"sample_questions": [{"id": _next_id(), "question": [q]} for q in sample_questions]},
        "data_sources": {"tables": tables},
        "instructions": {"text_instructions": text_instructions,
                         "example_question_sqls": example_question_sqls},
        "benchmarks": {"questions": benchmarks},
    }
