#!/usr/bin/env python3
"""Provision the *Strategic Spend Analytics* Genie space — metric-view-only.

This is the reproducible, parameterized way to (re)create the Genie space that
backs the app's ``ask_genie`` chatbot tool. It is the Genie analogue of
``metric_views/apply_metric_views.py``: catalog / schema / warehouse are
arguments, so the same definition deploys to dev and prod unchanged.

Design rules baked into the space:
  * METRIC VIEWS ONLY. The curated data sources are the five governed UC metric
    views in ``<catalog>.<schema_gold>`` — never raw fact / dim tables. Genie
    inherits every display name, synonym, and format from the metric-view YAML,
    and the governed per-line conditions (PAID / addressable / managed) can't
    drift from the app's KPIs.
  * The space answers the spend lifecycle: source/contract -> request -> order
    -> invoice -> paid.

Endpoints (see the genie-rooms skill):
  POST  /api/2.0/genie/spaces                                   create
  GET   /api/2.0/genie/spaces/{id}?include_serialized_space=true  fetch
  PATCH /api/2.0/genie/spaces/{id}                              update
  DELETE/trash via --delete (uses the same REST surface)

Auth is delegated to the Databricks CLI (`databricks api ...`) so this script
carries no credentials and honors the named --profile.

Examples
--------
  # Dry run — print the serialized_space and the outer payload, change nothing
  python genie/provision_genie_space.py --dry-run \
      --catalog horizontal_finance_dev --warehouse-id e9b34f7a2e4b0561

  # Create a fresh space (prints the new space_id; wire it into app.yaml)
  python genie/provision_genie_space.py --profile e2-demo-field-eng \
      --catalog horizontal_finance_dev --warehouse-id e9b34f7a2e4b0561 \
      --parent-path /Users/james.powers@databricks.com

  # Update an existing space in place (round-trips nothing — replaces the
  # curated definition this script owns)
  python genie/provision_genie_space.py --profile e2-demo-field-eng \
      --catalog horizontal_finance_dev --warehouse-id e9b34f7a2e4b0561 \
      --space-id 01f1...

  # Tear down + recreate from scratch
  python genie/provision_genie_space.py --profile e2-demo-field-eng \
      --catalog horizontal_finance_dev --warehouse-id e9b34f7a2e4b0561 \
      --space-id 01f1... --recreate --parent-path /Users/james.powers@databricks.com
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import itertools
import tempfile

# Genie validates that every id-keyed collection (sample_questions,
# text_instructions, example_question_sqls, benchmarks.questions) is sorted by
# id. Monotonic 32-char-hex ids assigned in insertion order satisfy that while
# preserving the authored display order.
_ID_COUNTER = itertools.count(1)


def _next_id() -> str:
    return f"{next(_ID_COUNTER):032x}"

DEFAULT_TITLE = "Strategic Spend Analytics"
DEFAULT_DESCRIPTION = (
    "End-to-end spend visibility across the procurement lifecycle "
    "(source/contract -> request -> order -> invoice -> paid). Ask about "
    "spend, suppliers, contracts, purchase orders, and sourcing savings. "
    "Answers are computed only from governed UC metric views."
)


def _lines(text: str) -> list[str]:
    """Split SQL/text into the line list Genie's serialized_space expects."""
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

    # ── Tables: metric views only, sorted by identifier (validation rule) ────
    tables = sorted(
        [{"identifier": ident} for ident in (mv_spend, mv_supplier, mv_contracts, mv_pos, mv_savings)],
        key=lambda t: t["identifier"],
    )

    # ── Sample questions (lightweight starters) ──────────────────────────────
    sample_questions = [
        "Who are my top 5 vendors by spend?",
        "What percent of our contracts have been utilized?",
        "Who do we have the best payment terms with for IT & Telecom spend?",
        "Who are our most reliable suppliers?",
        "What share of our spend is managed vs maverick?",
        "Which purchase request channels leak the most off-contract spend?",
    ]

    # ── Instructions ──────────────────────────────────────────────────────────
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

    # ── Curated example question -> SQL pairs ────────────────────────────────
    example_question_sqls = [
        {
            "id": _next_id(),
            "question": ["Who are my top 5 vendors by spend?"],
            "sql": _lines(
                f"SELECT supplier_name, MEASURE(total_spend) AS total_spend\n"
                f"FROM {mv_spend}\n"
                f"WHERE invoice_date >= date_sub(current_date(), 365)\n"
                f"GROUP BY supplier_name\n"
                f"ORDER BY total_spend DESC\n"
                f"LIMIT 5"
            ),
            "usage_guidance": ["Top vendors = realized paid spend over the trailing 12 months."],
        },
        {
            "id": _next_id(),
            "question": ["What percent of our contracts have been utilized?"],
            "sql": _lines(
                f"SELECT MEASURE(utilization_rate) AS contract_utilization,\n"
                f"       MEASURE(total_committed) AS total_committed,\n"
                f"       MEASURE(total_actual)    AS total_actual\n"
                f"FROM {mv_contracts}"
            ),
            "usage_guidance": [
                "Dollar-weighted utilization (actual/committed). Optionally GROUP BY "
                "contract_type, region, or supplier_name."
            ],
        },
        {
            "id": _next_id(),
            "question": ["Who do we have the best payment terms with for a given category?"],
            "sql": _lines(
                f"SELECT supplier_name, payment_terms, MEASURE(total_spend) AS spend\n"
                f"FROM {mv_spend}\n"
                f"WHERE category_primary = :category\n"
                f"  AND invoice_date >= date_sub(current_date(), 365)\n"
                f"GROUP BY supplier_name, payment_terms\n"
                f"ORDER BY payment_terms DESC, spend DESC\n"
                f"LIMIT 20"
            ),
            "parameters": [
                {
                    "name": "category",
                    "type_hint": "STRING",
                    "default_value": {"values": ["IT & Telecom"]},
                }
            ],
            "usage_guidance": ["Best terms = longest net terms (Net60 best). Filter by category_primary."],
        },
        {
            "id": _next_id(),
            "question": ["Who are our most reliable suppliers?"],
            "sql": _lines(
                f"SELECT supplier_name,\n"
                f"       MEASURE(reliability_score) AS reliability,\n"
                f"       MEASURE(governed_spend_pct) AS governed_pct,\n"
                f"       MEASURE(trailing_spend)     AS spend\n"
                f"FROM {mv_supplier}\n"
                f"WHERE invoice_date >= date_sub(current_date(), 365)\n"
                f"GROUP BY supplier_name\n"
                f"HAVING MEASURE(trailing_spend) > 1000000\n"
                f"ORDER BY reliability DESC\n"
                f"LIMIT 10"
            ),
            "usage_guidance": [
                "Reliability is a governance index (no delivery data exists). Filter to "
                "material suppliers so one-off vendors don't top the list."
            ],
        },
        {
            "id": _next_id(),
            "question": ["Which purchase request channels leak the most off-contract spend?"],
            "sql": _lines(
                f"SELECT pr_source,\n"
                f"       MEASURE(total_po_amount)     AS po_amount,\n"
                f"       MEASURE(off_contract_po_pct) AS off_contract_pct\n"
                f"FROM {mv_pos}\n"
                f"GROUP BY pr_source\n"
                f"ORDER BY off_contract_pct DESC"
            ),
            "usage_guidance": ["ManualSubmission and ProcurementAgent run the highest off-contract share."],
        },
        {
            "id": _next_id(),
            "question": ["How much have we saved through sourcing events by event type?"],
            "sql": _lines(
                f"SELECT event_type,\n"
                f"       MEASURE(total_savings)          AS savings,\n"
                f"       MEASURE(effective_savings_rate) AS savings_rate\n"
                f"FROM {mv_savings}\n"
                f"GROUP BY event_type\n"
                f"ORDER BY savings DESC"
            ),
        },
    ]

    # ── Benchmarks (the four target questions, with expected SQL) ────────────
    def _bench(question: str, sql: str) -> dict:
        return {
            "id": _next_id(),
            "question": [question],
            "answer": [{"format": "SQL", "content": _lines(sql)}],
        }

    benchmarks = [
        _bench(
            "Who are my top 5 vendors?",
            f"SELECT supplier_name, MEASURE(total_spend) AS total_spend\n"
            f"FROM {mv_spend}\n"
            f"WHERE invoice_date >= date_sub(current_date(), 365)\n"
            f"GROUP BY supplier_name ORDER BY total_spend DESC LIMIT 5",
        ),
        _bench(
            "What percent of contracts have been utilized?",
            f"SELECT MEASURE(utilization_rate) AS contract_utilization FROM {mv_contracts}",
        ),
        _bench(
            "Who are our most reliable suppliers?",
            f"SELECT supplier_name, MEASURE(reliability_score) AS reliability\n"
            f"FROM {mv_supplier}\n"
            f"WHERE invoice_date >= date_sub(current_date(), 365)\n"
            f"GROUP BY supplier_name HAVING MEASURE(trailing_spend) > 1000000\n"
            f"ORDER BY reliability DESC LIMIT 10",
        ),
        _bench(
            "What is our managed vs maverick spend?",
            f"SELECT MEASURE(managed_spend_pct) AS managed_pct,\n"
            f"       MEASURE(measured_maverick_pct) AS maverick_pct\n"
            f"FROM {mv_spend}\n"
            f"WHERE invoice_date >= date_sub(current_date(), 365)",
        ),
    ]

    return {
        "version": 2,
        "config": {
            "sample_questions": [{"id": _next_id(), "question": [q]} for q in sample_questions]
        },
        "data_sources": {"tables": tables},
        "instructions": {
            "text_instructions": text_instructions,
            "example_question_sqls": example_question_sqls,
        },
        "benchmarks": {"questions": benchmarks},
    }


def build_outer_payload(
    *, title: str, description: str, warehouse_id: str, serialized_space: dict, parent_path: str | None
) -> dict:
    payload = {
        "title": title,
        "description": description,
        "warehouse_id": warehouse_id,
        "serialized_space": json.dumps(serialized_space),
    }
    if parent_path:
        payload["parent_path"] = parent_path
    return payload


def databricks_api(method: str, path: str, *, profile: str, body: dict | None = None) -> dict:
    args = ["databricks", "api", method, path, "--profile", profile]
    tmp_path = None
    if body is not None:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            json.dump(body, fh)
            tmp_path = fh.name
        args += ["--json", f"@{tmp_path}"]
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"`{' '.join(args)}` failed:\n{proc.stderr.strip()}")
    out = proc.stdout.strip()
    return json.loads(out) if out else {}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Provision the Strategic Spend Analytics Genie space.")
    p.add_argument("--profile", default="e2-demo-field-eng", help="Databricks CLI profile.")
    p.add_argument("--catalog", default="horizontal_finance_dev", help="Target catalog (dev/prod).")
    p.add_argument("--schema-gold", default="gold", help="Gold schema holding the metric views.")
    p.add_argument("--warehouse-id", default="e9b34f7a2e4b0561", help="Serving warehouse for the space.")
    p.add_argument("--title", default=DEFAULT_TITLE)
    p.add_argument("--description", default=DEFAULT_DESCRIPTION)
    p.add_argument("--parent-path", default=None, help="Workspace folder for a NEW space (create only).")
    p.add_argument("--space-id", default=None, help="Existing space id to PATCH (or DELETE with --recreate).")
    p.add_argument("--recreate", action="store_true", help="With --space-id: delete it, then create fresh.")
    p.add_argument("--dry-run", action="store_true", help="Print payloads and exit; change nothing.")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    serialized = build_serialized_space(args.catalog, args.schema_gold)
    payload = build_outer_payload(
        title=args.title,
        description=args.description,
        warehouse_id=args.warehouse_id,
        serialized_space=serialized,
        parent_path=args.parent_path,
    )

    if args.dry_run:
        print("=== serialized_space ===")
        print(json.dumps(serialized, indent=2))
        print("\n=== outer payload (serialized_space stringified) ===")
        print(json.dumps({**payload, "serialized_space": "<json string, omitted>"}, indent=2))
        print(f"\nCurated metric views: {[t['identifier'] for t in serialized['data_sources']['tables']]}")
        return 0

    if args.space_id and not args.recreate:
        print(f"PATCH existing space {args.space_id} ...")
        resp = databricks_api("patch", f"/api/2.0/genie/spaces/{args.space_id}", profile=args.profile, body=payload)
        print(f"Updated: {resp.get('space_id', args.space_id)}")
        return 0

    if args.space_id and args.recreate:
        print(f"DELETE space {args.space_id} ...")
        databricks_api("delete", f"/api/2.0/genie/spaces/{args.space_id}", profile=args.profile)

    print("POST new space ...")
    resp = databricks_api("post", "/api/2.0/genie/spaces", profile=args.profile, body=payload)
    new_id = resp.get("space_id")
    print(f"Created space_id: {new_id}")
    print("Wire this id into apps/spend-analytics/app.yaml (GENIE_SPACE_ID) and config.py.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
