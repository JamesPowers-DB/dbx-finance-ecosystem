"""Procurement Chatbot endpoints — FMAPI tool-use + SSE streaming.

Single routing layer: the model picks tools (no force-routing heuristic).
Tools:
  1. find_suppliers(category, segment, top_n)
  2. get_active_contract(supplier_id)
  3. price_history(supplier_id, category)
  4. expiring_contracts(within_days, max_utilization_pct) — renewal-risk / unused
  5. savings_summary(fiscal_year?, fiscal_quarter?) — cost savings for a period
  6. submit_pr(supplier_id, line_items) — faked, MCP-style outcome; ALWAYS confirm first
  7. ask_genie(question) — open-ended analytics via the Genie space (OBO token)

submit_pr guardrails (faked outcome — no write):
  - Total > $25,000 → opens a Sourcing intake + routes to Sourcing & Contracting (no PR)
  - Regulated supplier → routes to Sourcing & Contracting for a compliance-reviewed event

Auth: FMAPI + Genie both run on the caller's OBO token (serving.serving-endpoints
and dashboards.genie scopes). This runtime exposes no SP M2M creds.
"""

from __future__ import annotations

import json
import logging
import hashlib
import uuid
from datetime import datetime
from typing import AsyncGenerator

import urllib.error
import urllib.request

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..auth import CallerIdentity, caller_identity
from ..config import get_settings
from ..db import fetch_all, fetch_one
from ..lakebase import db_conn
from ..models import ChatMessage, ChatSession, ChatSessionCreate

log = logging.getLogger("sourcing_portal.chatbot")

router = APIRouter(prefix="/chat", tags=["chatbot"])


# Genie status-polling backoff. Most Genie queries complete in 2-8 s; the
# old flat 2-second sleep added 1-2 s of perceived latency to every call
# (a 1-second query still cost ~2 s of polling overhead). Start aggressive
# at 0.5 s, ramp to 1 s, then settle at 2 s for the long tail. Total
# budget (60 iterations) stays roughly equivalent to the old 45 * 2 = 90 s
# ceiling.
_GENIE_POLL_INTERVALS = [0.5, 0.5, 0.5, 0.5, 1.0, 1.0, 1.0, 1.0, 2.0]
_GENIE_POLL_MAX_ATTEMPTS = 60

# PR self-service ceiling — totals above this route to Sourcing & Contracting
# instead of creating a PR (the submit_pr guardrail).
_PR_SELF_SERVICE_LIMIT = 25_000

# The 8 spend categories (fact_invoices.true_category_primary) — the only valid
# find_suppliers categories. dim_supplier.category_primary is a different, coarser
# taxonomy that does NOT align, so we rank by invoiced spend category instead.
_SPEND_CATEGORIES = [
    "Direct_Materials_Components", "Facilities_GA", "IT_Telecom", "Logistics",
    "MRO_Field_Services", "Professional_Services", "Raw_Materials", "Software_Cloud",
]


def _genie_poll_interval(attempt: int) -> float:
    """Return the sleep duration (seconds) for the given poll attempt index."""
    return _GENIE_POLL_INTERVALS[min(attempt, len(_GENIE_POLL_INTERVALS) - 1)]


# The app resolves its Genie space by TITLE (so a bundle-provisioned space needs
# no id written back into app.yaml). Cache the resolved id per title for the
# process lifetime.
_GENIE_SPACE_ID_CACHE: dict[str, str] = {}


def _resolve_genie_space_id(genie_request, token: str, title: str) -> str | None:
    """Find a Genie space id by exact title via the list API (paginated, cached)."""
    if title in _GENIE_SPACE_ID_CACHE:
        return _GENIE_SPACE_ID_CACHE[title]
    page_token = None
    for _ in range(20):
        path = "/api/2.0/genie/spaces?page_size=100" + (f"&page_token={page_token}" if page_token else "")
        res = genie_request("GET", path, token)
        for sp in res.get("spaces", []) or []:
            if sp.get("title") == title and sp.get("space_id"):
                _GENIE_SPACE_ID_CACHE[title] = sp["space_id"]
                return sp["space_id"]
        page_token = res.get("next_page_token")
        if not page_token:
            break
    return None

_SYSTEM_PROMPT = """You are the Spend Analytics Assistant for Strategic Spend Analytics — a
procurement agent that helps sourcing managers and buyers take action and get answers.

Tools:
- find_suppliers: recommend suppliers for a need. The `category` MUST be one of these 8 spend categories: Direct_Materials_Components, Facilities_GA, IT_Telecom, Logistics, MRO_Field_Services, Professional_Services, Raw_Materials, Software_Cloud. Map the user's need to the closest one — e.g. monitors/laptops/networking/phones/hardware → IT_Telecom; SaaS/licenses/cloud → Software_Cloud; office/cleaning/facilities → Facilities_GA; shipping/freight/warehousing → Logistics; consulting/legal/audit → Professional_Services; maintenance/repair/field service → MRO_Field_Services; components/parts/assemblies → Direct_Materials_Components; metals/polymers/chemicals → Raw_Materials. Do NOT pass the raw product name.
- supplier_profile: a specific supplier's scorecard (spend, on-time %, DPO, maverick %, terms, top categories, active contracts). Use whenever the user asks about ONE named supplier (pass supplier_id from a prior find_suppliers result, or supplier_name).
- get_active_contract: check a supplier's active contracts.
- price_history: recent unit prices paid to a supplier for a category.
- expiring_contracts: contracts expiring soon AND under-utilized (renewal risk / unused commitments).
- savings_summary: cost savings for a fiscal period (e.g. "last quarter").
- submit_pr: submit a purchase request. Large spend is auto-routed to Sourcing & Contracting.
- ask_genie: answer ANY open-ended analytics question about spend, suppliers, contracts, or savings via the governed Genie space. Use this whenever the dedicated tools don't directly cover the question.

Rules:
- Before calling submit_pr, show a one-line confirmation (supplier, items, total) and ask the user to confirm.
- submit_pr enforces a $25,000 self-service limit. Above it, it does NOT create a PR — it opens a Sourcing intake and routes to Sourcing & Contracting. Relay that outcome to the user.
- Never recommend regulated suppliers as sourcing/negotiation targets.
- Prefer the dedicated tools (find_suppliers, supplier_profile, get_active_contract, expiring_contracts, savings_summary, submit_pr). Use ask_genie ONLY for open-ended DATA analytics not covered by them (spend trends, breakdowns, rankings).
- Do NOT use any tool for meta or conversational requests (e.g. "summarize this chat", "what did I just ask", "give me the transcript"). Answer those directly from the conversation.
- ALWAYS identify suppliers by supplier_id, never by name. find_suppliers returns a supplier_id for every row — when the user picks one of those suppliers (by name, rank, or "that one"), reuse its supplier_id verbatim in supplier_profile / get_active_contract / price_history / submit_pr. Do NOT re-run find_suppliers and do NOT pass supplier_name when you already have the id. Pass supplier_name to supplier_profile only for a supplier the user names cold that was never in a prior result.

Output style:
- Use light Markdown for readability: **bold** for labels/key figures, "-" bullet lists, numbered lists, and Markdown tables for tabular data (e.g. ranked supplier lists or a profile scorecard). Keep tables compact.
- Do NOT use emojis or decorative symbols (no checkmarks, warning signs, etc.).
- Be concise and businesslike — no filler, no "Sure!"/"Here's", no exclamation marks. Lead with the answer.
- A short one-line intro before a table/list is fine; end with a brief next-step question only when useful.
"""

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "find_suppliers",
            "description": "Recommend non-regulated suppliers ranked by paid spend in a category. `category` MUST be one of: Direct_Materials_Components, Facilities_GA, IT_Telecom, Logistics, MRO_Field_Services, Professional_Services, Raw_Materials, Software_Cloud. Map the need to the closest (e.g. monitors/laptops/networking → IT_Telecom; software/SaaS → Software_Cloud; office/cleaning → Facilities_GA). Never pass a raw product name like 'monitors'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [
                            "Direct_Materials_Components", "Facilities_GA", "IT_Telecom", "Logistics",
                            "MRO_Field_Services", "Professional_Services", "Raw_Materials", "Software_Cloud",
                        ],
                        "description": "One of the 8 spend categories the need maps to.",
                    },
                    "region": {"type": "string", "description": "Optional region filter: NA, EMEA, APAC."},
                    "top_n": {"type": "integer", "default": 4},
                },
                "required": ["category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "supplier_profile",
            "description": "Get a single supplier's scorecard: region, payment terms, regulated flag, T12M paid spend, on-time payment %, avg DPO, maverick %, managed %, top spend categories, and active-contract count. Pass supplier_id if known, else supplier_name. Use when the user asks about a specific supplier.",
            "parameters": {
                "type": "object",
                "properties": {
                    "supplier_id": {"type": "string"},
                    "supplier_name": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_active_contract",
            "description": "Look up active Statement of Work or Framework contracts for a supplier.",
            "parameters": {
                "type": "object",
                "properties": {"supplier_id": {"type": "string"}},
                "required": ["supplier_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "price_history",
            "description": "Return recent unit prices paid to a supplier for a category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "supplier_id": {"type": "string"},
                    "category": {"type": "string"},
                },
                "required": ["supplier_id", "category"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "expiring_contracts",
            "description": "List active contracts that are expiring soon AND under-utilized (low % of committed spend consumed) — the renewal-risk / unused-commitment view. Use for questions like 'which contracts are about to expire and haven't been used'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "within_days": {"type": "integer", "default": 120, "description": "expiration horizon in days"},
                    "max_utilization_pct": {"type": "integer", "default": 50, "description": "only contracts consumed below this %"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "savings_summary",
            "description": "Summarize procurement cost savings for a fiscal period. Omit fiscal_year/fiscal_quarter to get the most recent period. Use for 'cost savings from last quarter' type questions.",
            "parameters": {
                "type": "object",
                "properties": {
                    "fiscal_year": {"type": "integer"},
                    "fiscal_quarter": {"type": "integer", "description": "1, 2, 3, or 4"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_pr",
            "description": "Submit a purchase request (demo action via the Procurement integration). ONLY call after the user confirms. Totals over $25,000 are auto-routed to Sourcing & Contracting instead of creating a PR.",
            "parameters": {
                "type": "object",
                "properties": {
                    "supplier_id": {"type": "string"},
                    "supplier_name": {"type": "string"},
                    "line_items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "description": {"type": "string"},
                                "quantity": {"type": "number"},
                                "unit_price": {"type": "number"},
                                "category": {"type": "string"},
                            },
                        },
                    },
                    "segment": {"type": "string"},
                    "justification": {"type": "string"},
                },
                "required": ["supplier_id", "line_items"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_genie",
            "description": "Answer an open-ended analytical question about spend, supplier performance, contracts, or cost savings via the Strategic Spend Analytics Genie space. Use for trends, breakdowns, rankings, or anything the other tools don't directly cover.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The natural language question to ask Genie."},
                },
                "required": ["question"],
            },
        },
    },
]


def _run_tool(name: str, args: dict, caller: CallerIdentity) -> str:
    s = get_settings()
    try:
        if name == "find_suppliers":
            category = (args.get("category") or "").strip()
            region = (args.get("region") or "").strip()
            top_n = int(args.get("top_n", 4))
            region_clause = "AND UPPER(ds.region) = UPPER(?)" if region else ""
            # Rank suppliers by PAID spend in the category they've actually been
            # invoiced in (true_category_primary/secondary — the 8-value spend
            # taxonomy). NB: dim_supplier.category_primary is a DIFFERENT, coarser
            # taxonomy that doesn't align with spend categories, and line
            # descriptions are synthetic — so neither is a reliable selector.
            # Non-regulated only. The category should be one of _SPEND_CATEGORIES;
            # a partial term (e.g. 'telecom') still matches via LIKE.
            like = f"%{category.lower()}%"
            rows = fetch_all(
                caller,
                f"""
                SELECT
                    fi.supplier_id,
                    MAX(ds.supplier_name)              AS supplier_name,
                    MAX(ds.region)                     AS region,
                    MAX(ds.payment_terms)              AS payment_terms,
                    MAX(fi.true_category_primary)      AS category,
                    ROUND(SUM(fi.amount), 2)           AS category_spend_usd,
                    COUNT(*)                           AS line_count
                FROM {s.gold}.gold_fact_invoices fi
                JOIN {s.gold}.gold_dim_supplier ds ON fi.supplier_id = ds.supplier_id
                WHERE fi.payment_status = 'PAID'
                  AND COALESCE(ds.is_regulated_supplier, FALSE) = FALSE
                  AND (LOWER(fi.true_category_primary) LIKE ? OR LOWER(fi.true_category_secondary) LIKE ?)
                  {region_clause}
                GROUP BY fi.supplier_id
                ORDER BY category_spend_usd DESC
                LIMIT ?
                """,
                [like, like] + ([region] if region else []) + [top_n],
            )
            if not rows:
                return json.dumps({
                    "found": False,
                    "message": f"No suppliers matched '{category}'{f' in {region}' if region else ''}.",
                    "valid_categories": _SPEND_CATEGORIES,
                    "hint": "Map the user's need to the closest category above and call find_suppliers again.",
                }, default=str)
            return json.dumps({"category_query": category, "region": region or "all", "suppliers": rows}, default=str)

        elif name == "supplier_profile":
            supplier_id = (args.get("supplier_id") or "").strip()
            supplier_name = (args.get("supplier_name") or "").strip()
            if not supplier_id and supplier_name:
                # Resolve a name → the highest paid-spend supplier carrying it.
                # Supplier names can collide across ids, so pick the most material
                # match deterministically rather than an arbitrary first row.
                hit = fetch_one(
                    caller,
                    f"""
                    SELECT fi.supplier_id
                    FROM {s.gold}.gold_fact_invoices fi
                    JOIN {s.gold}.gold_dim_supplier ds ON fi.supplier_id = ds.supplier_id
                    WHERE LOWER(ds.supplier_name) LIKE ? AND fi.payment_status = 'PAID'
                    GROUP BY fi.supplier_id
                    ORDER BY SUM(fi.amount) DESC
                    LIMIT 1
                    """,
                    [f"%{supplier_name.lower()}%"],
                )
                supplier_id = (hit or {}).get("supplier_id", "")
            if not supplier_id:
                return json.dumps({"found": False, "message": f"No supplier found matching '{supplier_name}'."})
            # Static supplier-master attributes (region, terms, regulated) come from
            # dim_supplier — the SAME source find_suppliers uses — so the two tools
            # never disagree on region. The metric view supplies the measures only.
            attrs = fetch_one(
                caller,
                f"""
                SELECT supplier_name, region, payment_terms,
                       is_regulated_supplier AS is_regulated
                FROM {s.gold}.gold_dim_supplier WHERE supplier_id = ?
                """,
                [supplier_id],
            ) or {}
            measures = fetch_one(
                caller,
                f"""
                SELECT ROUND(MEASURE(trailing_spend), 2)               AS t12m_spend,
                       ROUND(MEASURE(on_time_payment_pct) * 100, 1)    AS on_time_pct,
                       ROUND(MEASURE(avg_dpo), 1)                      AS avg_dpo,
                       ROUND(MEASURE(measured_maverick_pct) * 100, 1)  AS maverick_pct,
                       ROUND(MEASURE(managed_spend_pct) * 100, 1)      AS managed_pct
                FROM {s.gold}.gold_mv_supplier_performance
                WHERE supplier_id = ? AND invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
                GROUP BY ALL
                """,
                [supplier_id],
            ) or {}
            header = {"supplier_id": supplier_id, **attrs, **measures}
            top_categories = fetch_all(
                caller,
                f"""
                SELECT true_category_primary AS category, ROUND(SUM(amount), 2) AS spend_usd
                FROM {s.gold}.gold_fact_invoices
                WHERE supplier_id = ? AND payment_status = 'PAID'
                  AND invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
                GROUP BY true_category_primary ORDER BY spend_usd DESC LIMIT 3
                """,
                [supplier_id],
            )
            contracts = fetch_one(
                caller,
                f"""
                SELECT COUNT(*) AS active_contracts
                FROM {s.silver}.silver_contract_inbound
                WHERE supplier_id = ? AND status = 'Active'
                  AND contract_type IN ('Statement of Work', 'Framework')
                  AND effective_date <= CURRENT_DATE() AND expiration_date >= CURRENT_DATE()
                """,
                [supplier_id],
            ) or {}
            return json.dumps({
                "found": bool(attrs),
                "profile": header,
                "top_categories": top_categories,
                "active_contracts": int(contracts.get("active_contracts") or 0),
            }, default=str)

        elif name == "get_active_contract":
            supplier_id = args["supplier_id"]
            rows = fetch_all(
                caller,
                f"""
                SELECT contract_workspace_id, contract_type, title,
                       effective_date, expiration_date, total_committed_spend,
                       actual_spend_to_date, status
                FROM {s.silver}.silver_contract_inbound
                WHERE supplier_id = ?
                  AND contract_type IN ('Statement of Work', 'Framework')
                  AND status = 'Active'
                  AND effective_date <= CURRENT_DATE()
                  AND expiration_date >= CURRENT_DATE()
                ORDER BY expiration_date DESC
                LIMIT 5
                """,
                [supplier_id],
            )
            return json.dumps(rows, default=str)

        elif name == "price_history":
            supplier_id = args["supplier_id"]
            category = args["category"]
            # Quantity-weighted unit price; simple AVG ignores quantity mix
            # (a single $10/unit line counts equal to a 1000-unit $50 line).
            rows = fetch_all(
                caller,
                f"""
                SELECT fiscal_year, fiscal_quarter,
                       ROUND(SUM(unit_price * quantity) / NULLIF(SUM(quantity), 0), 4)
                           AS qty_weighted_unit_price,
                       SUM(quantity)                              AS total_quantity,
                       COUNT(*)                                   AS line_count
                FROM {s.gold}.gold_fact_invoices
                WHERE supplier_id = ?
                  AND true_category_secondary LIKE ?
                  AND payment_status = 'PAID'
                GROUP BY fiscal_year, fiscal_quarter
                ORDER BY fiscal_year DESC, fiscal_quarter DESC
                LIMIT 8
                """,
                [supplier_id, f"%{category}%"],
            )
            return json.dumps(rows, default=str)

        elif name == "expiring_contracts":
            within_days = int(args.get("within_days", 120))
            max_util = float(args.get("max_utilization_pct", 50))
            # Active contracts expiring within the horizon AND consumed below the
            # utilization cap — i.e. renewal-risk + unused commitments. Uses the
            # contract's own committed/actual figures (silver.contract_inbound).
            rows = fetch_all(
                caller,
                f"""
                SELECT contract_workspace_id, title, supplier_id,
                       expiration_date,
                       DATEDIFF(expiration_date, CURRENT_DATE()) AS days_to_expiry,
                       ROUND(total_committed_spend, 0) AS committed_usd,
                       ROUND(100.0 * actual_spend_to_date / NULLIF(total_committed_spend, 0), 1)
                           AS pct_consumed
                FROM {s.silver}.silver_contract_inbound
                WHERE contract_type IN ('Statement of Work', 'Framework')
                  AND status = 'Active'
                  AND expiration_date BETWEEN CURRENT_DATE() AND DATE_ADD(CURRENT_DATE(), ?)
                  AND COALESCE(100.0 * actual_spend_to_date / NULLIF(total_committed_spend, 0), 0) < ?
                ORDER BY days_to_expiry ASC
                LIMIT 15
                """,
                [within_days, max_util],
            )
            return json.dumps({
                "within_days": within_days,
                "max_utilization_pct": max_util,
                "count": len(rows),
                "contracts": rows,
            }, default=str)

        elif name == "savings_summary":
            fy = args.get("fiscal_year")
            fq = args.get("fiscal_quarter")
            # Default to the most recent period present in the savings fact.
            if not fy or not fq:
                latest = fetch_one(
                    caller,
                    f"""
                    SELECT fiscal_year, fiscal_quarter
                    FROM {s.gold}.gold_fact_cost_savings
                    ORDER BY fiscal_year DESC, fiscal_quarter DESC
                    LIMIT 1
                    """,
                ) or {}
                fy = fy or latest.get("fiscal_year")
                fq = fq or latest.get("fiscal_quarter")
            head = fetch_one(
                caller,
                f"""
                SELECT ROUND(SUM(savings_amount_usd), 2) AS total_savings_usd,
                       COUNT(*) AS event_count,
                       ROUND(AVG(savings_rate) * 100, 1) AS avg_savings_rate_pct
                FROM {s.gold}.gold_fact_cost_savings
                WHERE fiscal_year = ? AND fiscal_quarter = ?
                """,
                [fy, fq],
            ) or {}
            by_category = fetch_all(
                caller,
                f"""
                SELECT category_primary,
                       ROUND(SUM(savings_amount_usd), 2) AS savings_usd
                FROM {s.gold}.gold_fact_cost_savings
                WHERE fiscal_year = ? AND fiscal_quarter = ?
                GROUP BY category_primary
                ORDER BY savings_usd DESC
                LIMIT 5
                """,
                [fy, fq],
            )
            return json.dumps({
                "fiscal_year": fy,
                "fiscal_quarter": fq,
                "total_savings_usd": float(head.get("total_savings_usd") or 0),
                "event_count": int(head.get("event_count") or 0),
                "avg_savings_rate_pct": float(head.get("avg_savings_rate_pct") or 0),
                "top_categories": by_category,
            }, default=str)

        elif name == "submit_pr":
            # Demo action: this fabricates the outcome the way a Procurement MCP
            # server would surface a side-effect — no real write. Two guardrails:
            # large spend routes to Sourcing & Contracting; regulated suppliers
            # route to Compliance. Otherwise it "creates" a PR.
            supplier_id = args["supplier_id"]
            supplier_name = args.get("supplier_name") or supplier_id
            line_items = args.get("line_items") or []
            total = round(sum(float(li.get("unit_price", 0)) * float(li.get("quantity", 1)) for li in line_items), 2)
            line_count = len(line_items)
            first_desc = (line_items[0].get("description") if line_items else "") or "items"
            summary = first_desc if line_count <= 1 else f"{first_desc} (+{line_count - 1} more lines)"

            # Guardrail: regulated supplier → Compliance/Sourcing.
            supplier = fetch_one(
                caller,
                f"SELECT is_regulated_supplier FROM {s.gold}.gold_dim_supplier WHERE supplier_id = ?",
                [supplier_id],
            )
            if supplier and supplier.get("is_regulated_supplier"):
                intake_id = f"SR-{datetime.utcnow():%Y}-{uuid.uuid4().hex[:5].upper()}"
                return json.dumps({
                    "action": "route_to_sourcing",
                    "system": "Sourcing & Contracting (via Procurement MCP)",
                    "status": "escalated",
                    "intake_id": intake_id,
                    "supplier_name": supplier_name,
                    "total_usd": total,
                    "message": (
                        f"{supplier_name} is a regulated supplier — direct PRs aren't allowed. "
                        f"Opened Sourcing intake {intake_id} and routed to Sourcing & Contracting for a compliance-reviewed event. No PR was created."
                    ),
                })

            # Guardrail: large spend → Sourcing & Contracting.
            if total > _PR_SELF_SERVICE_LIMIT:
                intake_id = f"SR-{datetime.utcnow():%Y}-{uuid.uuid4().hex[:5].upper()}"
                return json.dumps({
                    "action": "route_to_sourcing",
                    "system": "Sourcing & Contracting (via Procurement MCP)",
                    "status": "escalated",
                    "intake_id": intake_id,
                    "supplier_name": supplier_name,
                    "total_usd": total,
                    "threshold_usd": _PR_SELF_SERVICE_LIMIT,
                    "message": (
                        f"${total:,.0f} exceeds the ${_PR_SELF_SERVICE_LIMIT:,.0f} self-service limit. "
                        f"Opened Sourcing intake {intake_id} ({summary}, {supplier_name}) and routed to Sourcing & Contracting "
                        f"to run a competitive event — no PR was created."
                    ),
                })

            # Within limit → "create" the PR.
            pr_number = f"PR-{datetime.utcnow():%Y}-{uuid.uuid4().hex[:5].upper()}"
            return json.dumps({
                "action": "create_purchase_request",
                "system": "SAP Ariba (via Procurement MCP)",
                "status": "submitted",
                "pr_number": pr_number,
                "supplier_id": supplier_id,
                "supplier_name": supplier_name,
                "total_usd": total,
                "line_count": line_count,
                "routed_to": "Accounts Payable (3-way match)",
                "message": (
                    f"Submitted {pr_number} to SAP Ariba via the Procurement MCP — "
                    f"{summary}, {supplier_name}, ${total:,.0f}. Routed to AP for 3-way match."
                ),
            })

        elif name == "ask_genie":
            import time, urllib.request, urllib.error
            question = args["question"]
            log.info("ask_genie invoked for question: %s", question[:200])
            # Genie runs as the calling user (OBO token has the dashboards.genie
            # scope). This app runtime does not expose SP M2M creds, so there is
            # no SP path. s.genie_space_id is an optional explicit override;
            # otherwise resolve by title.
            space_id = s.genie_space_id
            obo_token = caller.access_token
            if not obo_token:
                return json.dumps({
                    "error": "No user token available for Genie.",
                    "hint": "Genie requires the OBO context (dashboards.genie scope).",
                })
            host = s.databricks_host.rstrip("/")
            if not host.startswith("http"):
                host = f"https://{host}"
            question_sig = hashlib.sha1(question.encode("utf-8")).hexdigest()[:12]
            log.info("ask_genie auth_mode=sp_only question_sig=%s", question_sig)

            def genie_request(
                method: str,
                path: str,
                token: str,
                body: dict | None = None,
            ) -> dict:
                data = json.dumps(body).encode() if body else None
                req = urllib.request.Request(
                    f"{host}{path}",
                    data=data,
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json",
                    },
                    method=method,
                )
                try:
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        return json.loads(resp.read())
                except urllib.error.HTTPError as e:
                    body_txt = e.read().decode("utf-8", errors="replace")
                    log.warning(
                        "Genie API %s %s failed with HTTP %s: %s",
                        method, path, e.code, body_txt[:300]
                    )
                    try:
                        payload = json.loads(body_txt)
                    except json.JSONDecodeError:
                        payload = {"raw_body": body_txt[:1000]}
                    payload["_http_status"] = e.code
                    payload["_http_reason"] = str(e.reason)
                    payload["_path"] = path
                    return payload
                except Exception as exc:
                    log.exception("Genie API %s %s request failed", method, path)
                    return {
                        "error_code": "GENIE_REQUEST_FAILED",
                        "message": str(exc),
                        "_path": path,
                    }

            def run_genie_query(token: str, auth_mode: str) -> dict:
                start = genie_request(
                    "POST",
                    f"/api/2.0/genie/spaces/{space_id}/start-conversation",
                    token,
                    {"content": question},
                )
                conv_id = start.get("conversation_id")
                msg_id = start.get("message_id")
                if not conv_id or not msg_id:
                    detail = start.get("message") or start.get("error") or str(start)
                    return {
                        "ok": False,
                        "error": "Failed to start Genie conversation",
                        "detail": detail,
                        "raw": start,
                        "auth_mode": auth_mode,
                    }

                for attempt in range(_GENIE_POLL_MAX_ATTEMPTS):
                    time.sleep(_genie_poll_interval(attempt))
                    msg = genie_request(
                        "GET",
                        f"/api/2.0/genie/spaces/{space_id}/conversations/{conv_id}/messages/{msg_id}",
                        token,
                    )
                    status = msg.get("status")
                    if status == "COMPLETED":
                        attachments = msg.get("attachments", [])
                        query_att = next(
                            (a.get("query", {}) for a in attachments if "query" in a), {}
                        )
                        text_att = next(
                            (a.get("text", {}) for a in attachments if "text" in a), {}
                        )
                        answer = text_att.get("content", "") or query_att.get("description", "")

                        # Fetch the actual query-result to get a real row count.
                        # The Genie message attachment carries the SQL definition
                        # but NOT the executed rows — those live behind a separate
                        # /query-result endpoint that returns a Statement Execution
                        # API-shaped payload. Best-effort: if this call fails or
                        # the SQL never executed, row_count stays None and the
                        # UI renders "rows pending" instead of lying with "0 rows".
                        row_count = None
                        if query_att.get("query"):
                            qr = genie_request(
                                "GET",
                                f"/api/2.0/genie/spaces/{space_id}"
                                f"/conversations/{conv_id}/messages/{msg_id}/query-result",
                                token,
                            )
                            # Two possible shapes — newer API nests the SDK
                            # Statement Execution response, older returns it
                            # at the top level. Probe both.
                            sr = qr.get("statement_response") or qr
                            manifest = sr.get("manifest") or {}
                            row_count = (
                                manifest.get("total_row_count")
                                or manifest.get("total_chunk_row_count")
                            )
                            if row_count is None:
                                result_payload = sr.get("result") or {}
                                data_array = result_payload.get("data_array")
                                if data_array is not None:
                                    row_count = len(data_array)

                        return {
                            "ok": True,
                            "question": question,
                            "answer": answer,
                            "sql": query_att.get("query", ""),
                            "row_count": row_count,
                            "conv_id": conv_id,
                            "msg_id": msg_id,
                            "space_id": space_id,
                            "auth_mode": auth_mode,
                        }
                    if status in ("FAILED", "CANCELLED"):
                        return {
                            "ok": False,
                            "error": f"Genie query {status}",
                            "detail": msg.get("error", ""),
                            "auth_mode": auth_mode,
                        }
                    if msg.get("error_code"):
                        return {
                            "ok": False,
                            "error": msg.get("message", "Genie error"),
                            "error_code": msg.get("error_code"),
                            "detail": msg,
                            "auth_mode": auth_mode,
                        }

                return {
                    "ok": False,
                    "error": "Genie query timed out after 90 seconds. Try a simpler question.",
                    "auth_mode": auth_mode,
                }

            # Resolve the space by title (cached) unless explicitly pinned via
            # GENIE_SPACE_ID. run_genie_query closes over `space_id`.
            if not space_id:
                space_id = _resolve_genie_space_id(genie_request, obo_token, s.genie_space_title)
                if not space_id:
                    return json.dumps({
                        "error": f"No Genie space titled '{s.genie_space_title}' was found.",
                        "hint": "Provision it with `databricks bundle run setup` (or set GENIE_SPACE_ID).",
                    })

            result = run_genie_query(obo_token, "user_obo")
            if result.get("ok"):
                log.info("ask_genie succeeded question_sig=%s", question_sig)
                return json.dumps(result)
            log.warning("ask_genie failed question_sig=%s error=%s", question_sig, result.get("error"))
            return json.dumps({
                "error": result.get("error", "Genie query failed."),
                "detail": result.get("detail"),
                "hint": "Ensure the Genie space exists and you have CAN_VIEW access.",
            })

        else:
            return json.dumps({"error": f"Unknown tool: {name}"})
    except Exception as exc:
        log.exception("Tool %s failed", name)
        return json.dumps({"error": str(exc)})


# ── Session management ────────────────────────────────────────────────────────

@router.post("/sessions", response_model=ChatSession)
async def create_session(
    body: ChatSessionCreate,
    caller: CallerIdentity = Depends(caller_identity),
) -> dict:
    session_id = str(uuid.uuid4())
    now = datetime.utcnow()
    try:
        async with db_conn(caller) as conn:
            await conn.execute(
                "INSERT INTO chatbot_sessions (session_id, user_email, title, created_at, updated_at) VALUES (%s,%s,%s,%s,%s)",
                (session_id, caller.email, body.title, now, now),
            )
    except Exception:
        log.debug("Lakebase unavailable — session %s not persisted", session_id)
    return {"session_id": session_id, "title": body.title, "created_at": now, "updated_at": now}


@router.get("/sessions", response_model=list[ChatSession])
async def list_sessions(caller: CallerIdentity = Depends(caller_identity)) -> list[dict]:
    try:
        async with db_conn(caller) as conn:
            rows = await (await conn.execute(
                "SELECT session_id, title, created_at, updated_at FROM chatbot_sessions WHERE user_email = %s ORDER BY updated_at DESC LIMIT 20",
                (caller.email,),
            )).fetchall()
        return [{"session_id": r[0], "title": r[1], "created_at": r[2], "updated_at": r[3]} for r in rows]
    except Exception:
        log.debug("Lakebase unavailable — returning empty session list")
        return []


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    caller: CallerIdentity = Depends(caller_identity),
) -> dict:
    """Delete a conversation (and its messages via ON DELETE CASCADE). Scoped to
    the owner so a user can only delete their own sessions."""
    try:
        async with db_conn(caller) as conn:
            await conn.execute(
                "DELETE FROM chatbot_sessions WHERE session_id = %s AND user_email = %s",
                (session_id, caller.email),
            )
    except Exception as exc:
        log.warning("Failed to delete session %s: %s", session_id, exc)
        raise HTTPException(503, "Could not delete the conversation (Lakebase unavailable).")
    return {"ok": True, "session_id": session_id}


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessage])
async def get_messages(session_id: str, caller: CallerIdentity = Depends(caller_identity)) -> list[dict]:
    try:
        async with db_conn(caller) as conn:
            rows = await (await conn.execute(
                "SELECT message_id, session_id, role, content, tool_calls, created_at FROM chatbot_messages WHERE session_id = %s ORDER BY created_at",
                (session_id,),
            )).fetchall()
        return [
            {"message_id": r[0], "session_id": r[1], "role": r[2], "content": r[3],
             "tool_calls": r[4], "created_at": r[5]}
            for r in rows
        ]
    except Exception:
        log.debug("Lakebase unavailable — returning empty message list for %s", session_id)
        return []


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: str,
    body: dict,
    caller: CallerIdentity = Depends(caller_identity),
) -> StreamingResponse:
    user_content = body.get("content", "")
    if not user_content.strip():
        raise HTTPException(400, "content is required")

    # Persist user message and load history (best-effort — falls back to single-turn)
    history_rows: list[tuple] = []
    try:
        async with db_conn(caller) as conn:
            await conn.execute(
                "INSERT INTO chatbot_messages (message_id, session_id, role, content, created_at) VALUES (%s,%s,%s,%s,%s)",
                (str(uuid.uuid4()), session_id, "user", user_content, datetime.utcnow()),
            )
            history_rows = await (await conn.execute(
                "SELECT role, content FROM chatbot_messages WHERE session_id = %s ORDER BY created_at",
                (session_id,),
            )).fetchall()
    except Exception:
        log.debug("Lakebase unavailable — using single-turn context for session %s", session_id)

    messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
    messages += [{"role": r[0], "content": r[1]} for r in history_rows]
    # If Lakebase was unavailable, history_rows is empty; add the current user turn manually
    if not history_rows:
        messages.append({"role": "user", "content": user_content})

    return StreamingResponse(
        _stream_response(session_id, messages, caller),
        media_type="text/event-stream",
    )


class GuardrailBlocked(Exception):
    """The serving endpoint's AI Gateway safety guardrail rejected the request."""


def _query_fmapi(host: str, endpoint_name: str, access_token: str, messages: list[dict]) -> dict:
    """Call the FMAPI invocations endpoint directly via REST.

    Uses urllib (not the SDK) so tool-call requests work regardless of SDK
    version. The token should be an M2M token from the app's SP — not the
    user's OBO token — so FMAPI does not reject it with 403.
    """
    import urllib.request as _ur
    import urllib.error as _ue

    if not host.startswith("http"):
        host = f"https://{host}"
    url = f"{host.rstrip('/')}/serving-endpoints/{endpoint_name}/invocations"
    body = json.dumps({
        "messages": messages,
        "tools": _TOOLS,
        "max_tokens": 1024,
    }).encode()
    req = _ur.Request(
        url, data=body,
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with _ur.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read())
    except _ue.HTTPError as e:
        body_txt = e.read().decode("utf-8", errors="replace")
        if e.code == 400 and "guardrail" in body_txt.lower():
            raise GuardrailBlocked() from e
        raise RuntimeError(f"FMAPI HTTP {e.code}: {body_txt[:400]}") from e


async def _stream_response(
    session_id: str,
    messages: list[dict],
    caller: CallerIdentity,
) -> AsyncGenerator[str, None]:
    s = get_settings()
    full_response = ""
    tool_calls_buffer: list[dict] = []

    try:
        # Single routing layer: the model decides which tools to call (including
        # ask_genie for open-ended analytics) — no force-routing heuristic. FMAPI
        # runs as the calling user; the OBO token carries serving.serving-endpoints.
        fmapi_token = caller.access_token
        if not fmapi_token:
            yield f"data: {json.dumps({'type': 'error', 'message': 'No auth token available for the model endpoint.'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        import asyncio as _asyncio
        while True:
            raw = await _asyncio.to_thread(
                _query_fmapi,
                s.databricks_host, s.serving_endpoint_name, fmapi_token, messages,
            )

            choices = raw.get("choices", [])
            if not choices:
                break
            choice = choices[0]
            finish_reason = choice.get("finish_reason")
            msg = choice.get("message", {})

            content = msg.get("content") or ""
            if content:
                full_response += content
                yield f"data: {json.dumps({'type': 'content', 'text': content})}\n\n"

            tool_calls = msg.get("tool_calls") or []
            for tc in tool_calls:
                fn = tc.get("function", {})
                fn_name = fn.get("name", "")
                fn_args = json.loads(fn.get("arguments") or "{}")
                tc_id = tc.get("id", str(uuid.uuid4()))
                log.info("Tool call: %s", fn_name)
                yield f"data: {json.dumps({'type': 'tool_start', 'name': fn_name, 'args': fn_args})}\n\n"

                result = _run_tool(fn_name, fn_args, caller)
                yield f"data: {json.dumps({'type': 'tool_result', 'name': fn_name, 'result': result})}\n\n"

                tool_calls_buffer.append({"name": fn_name, "args": fn_args, "result": result})
                messages.append({"role": "assistant", "tool_calls": [tc]})
                messages.append({"role": "tool", "tool_call_id": tc_id, "content": result})

            if finish_reason == "stop" or (finish_reason != "tool_calls" and not tool_calls):
                break

        # Persist assistant reply (best-effort)
        try:
            async with db_conn(caller) as conn:
                await conn.execute(
                    "INSERT INTO chatbot_messages (message_id, session_id, role, content, tool_calls, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                    (str(uuid.uuid4()), session_id, "assistant", full_response,
                     json.dumps(tool_calls_buffer) if tool_calls_buffer else None,
                     datetime.utcnow()),
                )
                await conn.execute(
                    "UPDATE chatbot_sessions SET updated_at = %s WHERE session_id = %s",
                    (datetime.utcnow(), session_id),
                )
        except Exception:
            log.debug("Lakebase unavailable — assistant reply not persisted for session %s", session_id)

        yield f"data: {json.dumps({'type': 'done'})}\n\n"

    except GuardrailBlocked:
        log.warning("FMAPI request blocked by the endpoint's input/output guardrail")
        msg = (
            "I couldn't complete that — the model endpoint's safety guardrail flagged the request. "
            "This can false-trip on procurement data (e.g. aerospace/defense suppliers). "
            "Try rephrasing, or ask about a specific supplier or contract by name."
        )
        yield f"data: {json.dumps({'type': 'content', 'text': msg})}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    except Exception as exc:
        log.exception("Chatbot stream error")
        yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"


# ── Genie feedback ────────────────────────────────────────────────────────────

class GenieFeedbackBody(BaseModel):
    conv_id: str
    msg_id: str
    space_id: str
    rating: str  # "THUMBS_UP" or "THUMBS_DOWN"


@router.post("/genie-feedback")
async def genie_feedback(
    body: GenieFeedbackBody,
    caller: CallerIdentity = Depends(caller_identity),
) -> dict:
    s = get_settings()
    host = s.databricks_host.rstrip("/")
    if not host.startswith("http"):
        host = f"https://{host}"
    token = caller.access_token  # OBO token has dashboards.genie scope
    path = (
        f"/api/2.0/genie/spaces/{body.space_id}"
        f"/conversations/{body.conv_id}"
        f"/messages/{body.msg_id}/query-result/feedback"
    )
    req = urllib.request.Request(
        f"{host}{path}",
        data=json.dumps({"rating": body.rating}).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="PUT",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return {"ok": True, "status": resp.status}
    except urllib.error.HTTPError as e:
        body_txt = e.read().decode("utf-8", errors="replace")
        log.warning("Genie feedback PUT failed %s: %s", e.code, body_txt[:200])
        raise HTTPException(status_code=e.code, detail=body_txt)
    except Exception as exc:
        log.exception("Genie feedback request failed")
        raise HTTPException(status_code=500, detail=str(exc))
