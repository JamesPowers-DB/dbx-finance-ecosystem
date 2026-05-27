"""Procurement Chatbot endpoints — FMAPI tool-use + SSE streaming.

Tools the chatbot can call:
  1. suggest_supplier(category, segment, top_n)
  2. get_active_contract(supplier_id)
  3. price_history(supplier_id, category)
  4. check_sourcing_threshold(amount) — static $25k sourcing-manager rule
  5. get_remaining_budget(segment_code, fiscal_year, fiscal_quarter)
       — real budget vs paid-spend lookup against fact_fpa_budgets
  6. submit_pr(supplier_id, line_items) — writes to bronze_ariba; ALWAYS requires confirmation
  7. ask_genie(question) — natural-language analytics via Genie

PR submission guardrails:
  - Reject any total > $25,000 (sourcing-manager engagement threshold)
  - Reject regulated suppliers unless the user explicitly overrides
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

from databricks.sdk import WorkspaceClient
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..auth import CallerIdentity, caller_identity
from ..config import get_settings
from ..db import execute, fetch_all, fetch_one, t12m_supplier_spend_sql
from ..lakebase import db_conn
from ..models import ChatMessage, ChatSession, ChatSessionCreate

log = logging.getLogger("sourcing_portal.chatbot")

router = APIRouter(prefix="/chat", tags=["chatbot"])

_SYSTEM_PROMPT = """You are the Helios Procurement Assistant for the Strategic Sourcing Portal.
You help sourcing managers and buyers find the right suppliers, check active contracts,
understand price history, submit purchase requests, and explore spend analytics.

You have access to these tools:
- suggest_supplier: find candidate suppliers by category and segment
- get_active_contract: check for active contracts with a supplier
- price_history: review historical unit prices for a category/supplier
- check_sourcing_threshold: verify if an amount needs sourcing-manager escalation (static $25k rule)
- get_remaining_budget: look up the remaining FP&A budget for a segment/quarter (budget minus paid spend)
- submit_pr: submit a purchase request (always confirm with the user first)
- ask_genie: answer open-ended analytical questions about procurement spend, suppliers, contracts, or savings using natural language SQL (Helios Spend Analytics Genie Space)

Rules:
- ALWAYS show a confirmation summary and ask the user to confirm before calling submit_pr.
- NEVER submit a PR totaling more than $25,000 — tell the user they must escalate to a sourcing manager.
- NEVER suggest regulated suppliers for negotiation targets.
- When a buyer is sizing a PR against budget, prefer get_remaining_budget over check_sourcing_threshold — the former queries actual FP&A budget vs paid spend; the latter only enforces the static $25k policy threshold.
- Keep responses concise. Use bullet points for supplier suggestions.
- Use ask_genie for analytical questions like spend trends, rankings, breakdowns, or anything that requires querying data that isn't directly served by the other tools.
- If you cannot find a relevant supplier or contract, say so clearly.
"""

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "suggest_supplier",
            "description": "Find candidate suppliers for a spend category and optional segment. Returns top-N non-maverick, non-regulated suppliers with payment terms.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {"type": "string", "description": "Spend category (primary or secondary)"},
                    "segment": {"type": "string", "description": "Helios segment code (optional)"},
                    "top_n": {"type": "integer", "default": 3},
                },
                "required": ["category"],
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
                "properties": {
                    "supplier_id": {"type": "string"},
                },
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
            "name": "check_sourcing_threshold",
            "description": "Check whether an amount exceeds the $25,000 sourcing-manager engagement threshold. This is a static policy rule, NOT a budget check. Use get_remaining_budget for actual budget capacity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "amount": {"type": "number"},
                    "segment": {"type": "string"},
                },
                "required": ["amount"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_remaining_budget",
            "description": "Look up remaining FP&A budget for a segment and fiscal period. Returns budget_usd, paid_spend_usd, and remaining_usd from fact_fpa_budgets minus fact_invoices paid spend. Use this to size a PR against actual budget capacity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "segment_code": {"type": "string", "description": "Helios segment code (HAD, HPA, HSB, HET, CORP)"},
                    "fiscal_year": {"type": "integer"},
                    "fiscal_quarter": {"type": "integer", "description": "1, 2, 3, or 4"},
                },
                "required": ["segment_code", "fiscal_year", "fiscal_quarter"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ask_genie",
            "description": "Answer an open-ended analytical question about procurement spend, supplier performance, contracts, or cost savings using the Helios Spend Analytics Genie Space. Use when the user asks about spend trends, category breakdowns, supplier rankings, contract utilization, savings summaries, or any data question that the other tools don't directly cover.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "The natural language question to ask the Genie Space."},
                },
                "required": ["question"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_pr",
            "description": "Submit a purchase request to Ariba (demo: writes to bronze_ariba). ONLY call after user confirms.",
            "parameters": {
                "type": "object",
                "properties": {
                    "supplier_id": {"type": "string"},
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
]


def _run_tool(name: str, args: dict, caller: CallerIdentity) -> str:
    s = get_settings()
    try:
        if name == "suggest_supplier":
            category = args["category"]
            segment = args.get("segment")
            top_n = int(args.get("top_n", 3))
            params: list = [f"%{category}%"]
            seg_filter = ""
            if segment:
                seg_filter = "AND s.segment_affinity LIKE ?"
                params.append(f"%{segment}%")
            # Recommendation filter: prefer suppliers whose measured maverick %
            # is < 15% (i.e. most of their spend is contract-matched). Suppliers
            # with no T12M paid spend fall through with NULL maverick — keep
            # them in the result set instead of excluding (NULL means "no
            # observed spend yet", not "bad"), but rank them lower via
            # NULLS LAST on trailing_12m_spend.
            rows = fetch_all(
                caller,
                f"""
                SELECT s.supplier_id, s.supplier_name, s.payment_terms,
                       s.region,
                       agg.trailing_12m_spend,
                       agg.measured_maverick_pct
                FROM {s.gold}.dim_supplier s
                LEFT JOIN (
                    SELECT
                        i.supplier_id,
                        SUM(i.amount) AS trailing_12m_spend,
                        ROUND(100.0 * SUM(CASE WHEN NOT EXISTS (
                            SELECT 1 FROM {s.silver}.contract_inbound c
                            WHERE c.supplier_id = i.supplier_id
                              AND c.status = 'Active'
                              AND c.contract_type IN ('Statement of Work', 'Framework')
                              AND i.invoice_date BETWEEN c.effective_date AND c.expiration_date
                        ) THEN i.amount ELSE 0 END) / NULLIF(SUM(i.amount), 0), 1)
                            AS measured_maverick_pct
                    FROM {s.gold}.fact_invoices i
                    WHERE i.invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
                      AND i.payment_status = 'PAID'
                    GROUP BY i.supplier_id
                ) agg ON s.supplier_id = agg.supplier_id
                WHERE (s.category_primary LIKE ? {seg_filter})
                  AND COALESCE(s.is_regulated_supplier, FALSE) = FALSE
                  AND COALESCE(agg.measured_maverick_pct, 0.0) < 15.0
                ORDER BY trailing_12m_spend DESC NULLS LAST
                LIMIT ?
                """,
                params + [top_n],
            )
            return json.dumps(rows, default=str)

        elif name == "get_active_contract":
            supplier_id = args["supplier_id"]
            rows = fetch_all(
                caller,
                f"""
                SELECT contract_workspace_id, contract_type, title,
                       effective_date, expiration_date, total_committed_spend,
                       actual_spend_to_date, status
                FROM {s.silver}.contract_inbound
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
                FROM {s.gold}.fact_invoices
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

        elif name == "check_sourcing_threshold":
            amount = float(args["amount"])
            if amount > 25_000:
                return json.dumps({
                    "exceeds_threshold": True,
                    "threshold": 25000,
                    "rule": "policy",
                    "message": "Amount exceeds the $25,000 sourcing-manager threshold. This PR requires sourcing-manager approval before submission.",
                })
            return json.dumps({"exceeds_threshold": False, "threshold": 25000, "rule": "policy"})

        elif name == "get_remaining_budget":
            segment_code = args["segment_code"]
            fy = int(args["fiscal_year"])
            fq = int(args["fiscal_quarter"])
            # Compare planned operating-expense budget (COGS + SGA in the
            # FP&A planning schema — there's no single 'EXPENSE' account_type)
            # vs realized (paid) spend for the same segment/period. Returns
            # the genuine remaining capacity — the previous
            # check_budget_threshold tool only checked a hardcoded $25k
            # policy rule and never queried budgets at all.
            row = fetch_one(
                caller,
                f"""
                WITH b AS (
                    SELECT SUM(amount_usd) AS budget_usd
                    FROM {s.gold}.fact_fpa_budgets
                    WHERE segment_code = ?
                      AND fiscal_year  = ?
                      AND fiscal_quarter = ?
                      AND account_type IN ('COGS', 'SGA')
                ),
                spent AS (
                    SELECT SUM(amount) AS paid_spend_usd
                    FROM {s.gold}.fact_invoices
                    WHERE segment_code = ?
                      AND fiscal_year  = ?
                      AND fiscal_quarter = ?
                      AND payment_status = 'PAID'
                )
                SELECT
                    COALESCE(b.budget_usd, 0)       AS budget_usd,
                    COALESCE(spent.paid_spend_usd, 0) AS paid_spend_usd,
                    COALESCE(b.budget_usd, 0) - COALESCE(spent.paid_spend_usd, 0)
                        AS remaining_usd
                FROM b CROSS JOIN spent
                """,
                [segment_code, fy, fq, segment_code, fy, fq],
            )
            row = row or {}
            return json.dumps({
                "segment_code": segment_code,
                "fiscal_year": fy,
                "fiscal_quarter": fq,
                "budget_usd": float(row.get("budget_usd") or 0),
                "paid_spend_usd": float(row.get("paid_spend_usd") or 0),
                "remaining_usd": float(row.get("remaining_usd") or 0),
                "source": f"{s.gold}.fact_fpa_budgets (COGS+SGA) vs {s.gold}.fact_invoices (PAID)",
            })

        elif name == "submit_pr":
            supplier_id = args["supplier_id"]
            line_items = args["line_items"]
            segment = args.get("segment", "CORP")
            total = sum(float(li.get("unit_price", 0)) * float(li.get("quantity", 1)) for li in line_items)

            # Guardrail 1: amount
            if total > 25_000:
                return json.dumps({
                    "error": "PR rejected: total exceeds $25,000 sourcing-manager threshold.",
                    "total": total,
                })

            # Guardrail 2: regulated supplier
            supplier = fetch_one(
                caller,
                f"SELECT is_regulated_supplier FROM {s.gold}.dim_supplier WHERE supplier_id = ?",
                [supplier_id],
            )
            if supplier and supplier.get("is_regulated_supplier"):
                return json.dumps({
                    "error": "PR rejected: supplier is flagged as regulated. Contact sourcing manager to override.",
                    "supplier_id": supplier_id,
                })

            pr_number = f"PR-{uuid.uuid4().hex[:8].upper()}"
            pr_header_id = f"EBAN-{uuid.uuid4().hex[:10].upper()}"
            now_str = datetime.utcnow().isoformat()

            # Demo write: INSERT into bronze_ariba (pipeline picks up on next refresh)
            for i, li in enumerate(line_items, 1):
                execute(
                    caller,
                    f"""
                    INSERT INTO {s.catalog}.bronze_ariba.EBAN_PR_LINE
                    (pr_header_id, pr_number, line_number, description, quantity,
                     unit_price, amount, category, segment_code, supplier_id,
                     status, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SUBMITTED', ?)
                    """,
                    [
                        pr_header_id, pr_number, i,
                        li.get("description", ""), float(li.get("quantity", 1)),
                        float(li.get("unit_price", 0)),
                        float(li.get("quantity", 1)) * float(li.get("unit_price", 0)),
                        li.get("category", ""), segment, supplier_id, now_str,
                    ],
                )

            return json.dumps({
                "success": True,
                "pr_number": pr_number,
                "total": round(total, 2),
                "line_count": len(line_items),
                "message": f"Purchase request {pr_number} submitted successfully. The lakehouse pipeline will pick it up on the next refresh.",
            })

        elif name == "ask_genie":
            import time, urllib.request, urllib.error
            question = args["question"]
            log.info("ask_genie invoked for question: %s", question[:200])
            space_id = s.genie_space_id
            if not space_id:
                log.warning("ask_genie missing GENIE_SPACE_ID")
                return json.dumps({"error": "GENIE_SPACE_ID not configured in app.yaml."})
            if not s.sp_client_id or not s.sp_client_secret:
                log.warning("ask_genie missing APP_SP_CLIENT_ID/APP_SP_CLIENT_SECRET")
                return json.dumps({
                    "error": "Service principal credentials are missing for Genie.",
                    "detail": "APP_SP_CLIENT_ID and APP_SP_CLIENT_SECRET must be set in the app runtime.",
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

                for _ in range(45):
                    time.sleep(2)
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
                        return {
                            "ok": True,
                            "question": question,
                            "answer": answer,
                            "sql": query_att.get("query", ""),
                            "row_count": len(query_att.get("rows", [])),
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

            # Try SP M2M token first; fall back to user OBO token (has dashboards.genie scope).
            sp_token = (
                _get_sp_token(s.databricks_host, s.sp_client_id, s.sp_client_secret)
                if s.sp_client_id and s.sp_client_secret
                else None
            )
            if sp_token:
                sp_result = run_genie_query(sp_token, "app_service_principal")
                if sp_result.get("ok"):
                    log.info("ask_genie succeeded via service principal question_sig=%s", question_sig)
                    return json.dumps(sp_result)
                log.warning(
                    "ask_genie failed via service principal question_sig=%s error=%s — trying OBO",
                    question_sig,
                    sp_result.get("error"),
                )

            obo_token = caller.access_token
            if obo_token:
                obo_result = run_genie_query(obo_token, "user_obo")
                if obo_result.get("ok"):
                    log.info("ask_genie succeeded via OBO token question_sig=%s", question_sig)
                    return json.dumps(obo_result)
                log.warning(
                    "ask_genie failed via OBO token question_sig=%s error=%s",
                    question_sig,
                    obo_result.get("error"),
                )
                return json.dumps({
                    "error": "Genie query failed for both service principal and user OBO token.",
                    "detail": obo_result,
                    "hint": "Ensure the Genie Space ID is correct and the SP/user has CAN_VIEW access.",
                })

            return json.dumps({
                "error": "No valid token available for Genie (SP credentials failed, no OBO token).",
                "hint": "Deploy with OBO scopes including dashboards.genie.",
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


import time as _time
_sp_token_cache: dict = {}


def _get_sp_token(host: str, client_id: str, client_secret: str) -> str | None:
    """Obtain an M2M OAuth token using the app's SP credentials.

    Caches the token and refreshes 5 minutes before expiry to avoid
    per-request token fetches on back-to-back messages.

    Returns None (instead of raising) if the OIDC call fails for any reason
    so callers can fall back to the user's OBO access_token.
    """
    import urllib.request as _ur2
    import urllib.parse as _up

    now = _time.time()
    cached = _sp_token_cache.get("token")
    if cached and _sp_token_cache.get("expires_at", 0) > now + 300:
        return cached

    if not host.startswith("http"):
        host = f"https://{host}"
    data = _up.urlencode({
        "grant_type": "client_credentials",
        "scope": "all-apis",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode()
    req = _ur2.Request(
        f"{host}/oidc/v1/token", data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with _ur2.urlopen(req, timeout=15) as resp:
            td = json.loads(resp.read())
        _sp_token_cache["token"] = td["access_token"]
        _sp_token_cache["expires_at"] = now + td.get("expires_in", 3600)
        return td["access_token"]
    except Exception as exc:
        log.warning(
            "SP M2M token fetch failed (%s) — will fall back to OBO token. "
            "Check that DATABRICKS_CLIENT_ID/SECRET are valid OAuth M2M credentials.",
            exc,
        )
        return None


def _should_force_genie(question: str) -> bool:
    q = (question or "").lower()
    analytics_signals = [
        "total spend",
        "spend by",
        "by category",
        "top suppliers",
        "trailing 12",
        "contracts expire",
        "maverick spend",
        "savings",
        "trend",
        "breakdown",
    ]
    operational_signals = [
        "submit pr",
        "purchase request",
        "supplier suggestion",
        "suggest supplier",
        "active contract for supplier",
        "price history",
    ]
    if any(s in q for s in operational_signals):
        return False
    return any(s in q for s in analytics_signals)


def _question_sig(question: str) -> str:
    return hashlib.sha1((question or "").encode("utf-8")).hexdigest()[:12]


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
        raise RuntimeError(f"FMAPI HTTP {e.code}: {body_txt[:400]}") from e


async def _stream_response(
    session_id: str,
    messages: list[dict],
    caller: CallerIdentity,
) -> AsyncGenerator[str, None]:
    s = get_settings()
    user_question = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            user_question = m.get("content", "")
            break

    full_response = ""
    tool_calls_buffer: list[dict] = []

    try:
        force_genie = _should_force_genie(user_question)
        log.info(
            "routing_decision session_id=%s force_genie=%s question_sig=%s",
            session_id,
            force_genie,
            _question_sig(user_question),
        )
        # Deterministic routing for analytics prompts: call Genie directly so the
        # assistant cannot "miss" the ask_genie tool and hallucinate auth errors.
        if force_genie:
            log.info("Force-routing prompt to ask_genie: %s", user_question[:200])
            raw = _run_tool("ask_genie", {"question": user_question}, caller)
            tool_calls_buffer.append({
                "name": "ask_genie",
                "args": {"question": user_question},
                "result": raw,
            })
            yield f"data: {json.dumps({'type': 'tool_start', 'name': 'ask_genie', 'args': {'question': user_question}})}\n\n"
            yield f"data: {json.dumps({'type': 'tool_result', 'name': 'ask_genie', 'result': raw})}\n\n"
            try:
                payload = json.loads(raw)
                if payload.get("answer"):
                    full_response = payload.get("answer", "")
                else:
                    full_response = payload.get("error", "I couldn't retrieve an answer from Genie.")
                    if payload.get("detail"):
                        full_response += f" Details: {payload.get('detail')}"
            except Exception:
                full_response = raw
            if full_response:
                yield f"data: {json.dumps({'type': 'content', 'text': full_response})}\n\n"
            try:
                async with db_conn(caller) as conn:
                    await conn.execute(
                        "INSERT INTO chatbot_messages (message_id, session_id, role, content, tool_calls, created_at) VALUES (%s,%s,%s,%s,%s,%s)",
                        (str(uuid.uuid4()), session_id, "assistant", full_response,
                         json.dumps(tool_calls_buffer),
                         datetime.utcnow()),
                    )
                    await conn.execute(
                        "UPDATE chatbot_sessions SET updated_at = %s WHERE session_id = %s",
                        (datetime.utcnow(), session_id),
                    )
            except Exception:
                log.debug("Lakebase unavailable — assistant reply not persisted for session %s", session_id)
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        # Use SP M2M token for FMAPI so the LLM call runs as the app's SP (full
        # workspace access) rather than as the OBO user. _get_sp_token returns None
        # instead of raising, so fall back to the caller's OBO access_token.
        # The OBO token has the serving.serving-endpoints scope (declared in app.yaml).
        fmapi_token: str | None = None
        if s.sp_client_id and s.sp_client_secret:
            fmapi_token = _get_sp_token(s.databricks_host, s.sp_client_id, s.sp_client_secret)
            if fmapi_token is None:
                log.warning("SP M2M token unavailable — falling back to OBO token for FMAPI")
        if not fmapi_token:
            fmapi_token = caller.access_token
        if not fmapi_token:
            yield f"data: {json.dumps({'type': 'error', 'message': 'No auth token available for FMAPI (SP failed, no OBO token).'})}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            return

        while True:
            import asyncio as _asyncio
            raw = await _asyncio.to_thread(
                _query_fmapi,
                s.databricks_host, s.serving_endpoint_name, fmapi_token, messages
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
                log.info("Tool call started: %s", fn_name)
                yield f"data: {json.dumps({'type': 'tool_start', 'name': fn_name, 'args': fn_args})}\n\n"

                result = _run_tool(fn_name, fn_args, caller)
                yield f"data: {json.dumps({'type': 'tool_result', 'name': fn_name, 'result': result})}\n\n"

                tool_calls_buffer.append({"name": fn_name, "args": fn_args, "result": result})
                messages.append({"role": "assistant", "tool_calls": [tc]})
                messages.append({"role": "tool", "tool_call_id": tc_id, "content": result})

            if finish_reason == "stop" or (finish_reason != "tool_calls" and not tool_calls):
                break

        tool_names = [tc.get("name") for tc in tool_calls_buffer]
        if force_genie and "ask_genie" not in tool_names:
            log.warning(
                "ask_genie missing from FMAPI tool calls; forcing fallback session_id=%s question_sig=%s",
                session_id,
                _question_sig(user_question),
            )
            raw = _run_tool("ask_genie", {"question": user_question}, caller)
            tool_calls_buffer.append({
                "name": "ask_genie",
                "args": {"question": user_question},
                "result": raw,
            })
            yield f"data: {json.dumps({'type': 'tool_start', 'name': 'ask_genie', 'args': {'question': user_question}})}\n\n"
            yield f"data: {json.dumps({'type': 'tool_result', 'name': 'ask_genie', 'result': raw})}\n\n"
            try:
                payload = json.loads(raw)
                if payload.get("answer"):
                    full_response = payload.get("answer", "")
                else:
                    full_response = payload.get("error", "I couldn't retrieve an answer from Genie.")
                    if payload.get("detail"):
                        full_response += f" Details: {payload.get('detail')}"
            except Exception:
                full_response = raw
            yield f"data: {json.dumps({'type': 'content', 'text': full_response})}\n\n"

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
