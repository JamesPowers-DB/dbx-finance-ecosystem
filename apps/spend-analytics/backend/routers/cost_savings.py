"""Cost Savings Register — one unified ledger.

Every logged saving (Cost Reduction = hard, or Cost Avoidance = soft) is a row in
the Lakebase `savings_register` table, tied to a real artifact (a sourcing event
or a contract) and carried through a two-step workflow:

    submit  (status='pending', submitted_by)  →  attest (status='attested', attested_by)
                                              →  reject (status='rejected', reason)

A second person must attest (you cannot attest your own submission). Only attested
records count toward headline savings. The register is seeded once (idempotently)
from real sourcing events + contracts so the demo opens with populated, artifact-
tied history and a few pending items to action live.

Analytics surfaces (Genie's mv_cost_savings, the dashboard) are unchanged — they
read the governed metric views; this router owns only the operational ledger.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import CallerIdentity, caller_identity
from ..config import get_settings
from ..db import fetch_all, fetch_one
from ..lakebase import db_conn
from ..models import SavingsSubmit, SavingsRejectBody

router = APIRouter(prefix="/cost_savings", tags=["cost_savings"])

# ── Savings taxonomy ──────────────────────────────────────────────────────────
# key → (class, label). Class: 'reduction' (hard) | 'avoidance' (soft).
SAVINGS_TYPES: dict[str, tuple[str, str]] = {
    "unit_price_reduction": ("reduction", "Unit price reduction vs. prior contract/PO"),
    "renegotiation":        ("reduction", "Renegotiation of existing contract (mid-term decrease)"),
    "competitive_bid":      ("reduction", "Competitive bid / reverse auction below incumbent"),
    "rebates_volume":       ("reduction", "Rebates & volume discounts captured"),
    "spec_demand":          ("reduction", "Specification change or demand reduction"),
    "below_quote":          ("avoidance", "Negotiated below initial supplier quote"),
    "avoided_increase":     ("avoidance", "Avoided supplier price increase"),
    "held_flat":            ("avoidance", "Held price flat vs. inflation / market index"),
    "below_should_cost":    ("avoidance", "New-buy below should-cost / benchmark"),
    "value_adds":           ("avoidance", "Value-adds at no cost (freight, warranty, SLAs)"),
}

_REGISTER_COLS = (
    "record_id, artifact_type, artifact_id, artifact_title, savings_class, savings_type, "
    "supplier_id, supplier_name, segment_code, fiscal_year, fiscal_quarter, "
    "baseline_amount_usd, realized_amount_usd, savings_amount_usd, baseline_context, notes, "
    "submitted_by, submitted_at, status, attested_by, attested_at, rejection_reason"
)
_REGISTER_COL_NAMES = [c.strip() for c in _REGISTER_COLS.split(",")]

_INSERT_SQL = f"""
    INSERT INTO savings_register ({_REGISTER_COLS})
    VALUES ({', '.join(['%s'] * len(_REGISTER_COL_NAMES))})
    ON CONFLICT (record_id) DO NOTHING
"""


def _jsonable(v):
    return float(v) if isinstance(v, Decimal) else v


def _row(row: tuple) -> dict:
    return {c: _jsonable(v) for c, v in zip(_REGISTER_COL_NAMES, row)}


# ── Seed (idempotent, from real artifacts) ────────────────────────────────────
_seed_checked = False

_SUBMITTERS = [
    "maria.lopez@example.com", "david.chen@example.com", "priya.nair@example.com",
    "tom.becker@example.com", "sara.kim@example.com",
]
_ATTESTERS = ["lisa.grant@example.com", "ravi.patel@example.com", "category.lead@example.com"]
_REDUCTION_TYPES = ["competitive_bid", "unit_price_reduction", "renegotiation", "rebates_volume", "spec_demand"]
_AVOIDANCE_TYPES = ["below_quote", "avoided_increase", "held_flat", "below_should_cost", "value_adds"]
_AVOIDANCE_PCT = [0.045, 0.055, 0.035, 0.060, 0.050]


def _status_for(i: int) -> str:
    m = i % 10
    if m == 9:
        return "rejected"
    if m in (7, 8):
        return "pending"
    return "attested"


def _build_seed_rows(reductions: list[dict], contracts: list[dict]) -> list[tuple]:
    now = datetime.utcnow()
    rows: list[tuple] = []

    for i, r in enumerate(reductions):
        stype = _REDUCTION_TYPES[i % len(_REDUCTION_TYPES)]
        status = _status_for(i)
        attested_by = _ATTESTERS[i % len(_ATTESTERS)] if status == "attested" else None
        attested_at = now if status == "attested" else None
        reason = "Baseline not substantiated — resubmit with prior-PO reference." if status == "rejected" else None
        rows.append((
            f"SR-RED-{i:04d}", "sourcing_event", r["source_id"], r.get("event_title"),
            "reduction", stype, r.get("supplier_id"), r.get("supplier_name"), r.get("segment_code"),
            int(r["fiscal_year"]), int(r["fiscal_quarter"]),
            r.get("baseline_amount"), r.get("awarded_amount"), r.get("savings_amount_usd"),
            f"{r.get('event_type', 'Sourcing')} award vs. incumbent/prior pricing.", None,
            _SUBMITTERS[i % len(_SUBMITTERS)], now, status, attested_by, attested_at, reason,
        ))

    base = len(reductions)
    for j, c in enumerate(contracts):
        stype = _AVOIDANCE_TYPES[j % len(_AVOIDANCE_TYPES)]
        committed = float(c.get("committed") or 0)
        savings = round(committed * _AVOIDANCE_PCT[j % len(_AVOIDANCE_PCT)], 2)
        baseline = round(committed + savings, 2)  # would-have-paid
        i = base + j
        status = _status_for(i)
        attested_by = _ATTESTERS[j % len(_ATTESTERS)] if status == "attested" else None
        attested_at = now if status == "attested" else None
        reason = "Benchmark source unclear — attach should-cost model." if status == "rejected" else None
        rows.append((
            f"SR-AVD-{j:04d}", "contract", c["artifact_id"], c.get("title"),
            "avoidance", stype, c.get("supplier_id"), c.get("supplier_name"), None,
            int(c["fy"]), int(c["fq"]),
            baseline, committed, savings,
            f"Avoided cost vs. initial quote/benchmark on {c.get('title') or 'contract'}.", None,
            _SUBMITTERS[j % len(_SUBMITTERS)], now, status, attested_by, attested_at, reason,
        ))

    return rows


async def _ensure_seeded(caller: CallerIdentity) -> None:
    """Seed the register once from real sourcing events + contracts if it's empty."""
    global _seed_checked
    if _seed_checked:
        return
    s = get_settings()
    async with db_conn(caller) as conn:
        cnt = (await (await conn.execute("SELECT COUNT(*) FROM savings_register")).fetchone())[0]
        if cnt and int(cnt) > 0:
            _seed_checked = True
            return
        reductions = fetch_all(
            caller,
            f"""
            SELECT source_id, event_title, supplier_id, supplier_name, segment_code,
                   fiscal_year, fiscal_quarter,
                   ROUND(baseline_amount, 2)    AS baseline_amount,
                   ROUND(awarded_amount, 2)     AS awarded_amount,
                   ROUND(savings_amount_usd, 2) AS savings_amount_usd,
                   event_type
            FROM {s.gold}.fact_cost_savings
            ORDER BY savings_amount_usd DESC
            LIMIT 24
            """,
        )
        contracts = fetch_all(
            caller,
            f"""
            SELECT c.contract_workspace_id AS artifact_id, c.title,
                   c.supplier_id, sup.supplier_name,
                   YEAR(c.effective_date)    AS fy,
                   QUARTER(c.effective_date) AS fq,
                   ROUND(c.total_committed_spend, 2) AS committed
            FROM {s.silver}.contract_inbound c
            LEFT JOIN {s.gold}.dim_supplier sup ON c.supplier_id = sup.supplier_id
            WHERE c.contract_type IN ('Statement of Work', 'Framework')
              AND c.status = 'Active'
              AND c.effective_date <= CURRENT_DATE()
              AND c.expiration_date >= CURRENT_DATE()
            ORDER BY c.total_committed_spend DESC
            LIMIT 18
            """,
        )
        rows = _build_seed_rows(reductions, contracts)
        if rows:
            async with conn.cursor() as cur:
                await cur.executemany(_INSERT_SQL, rows)
    _seed_checked = True


# ── Endpoints ─────────────────────────────────────────────────────────────────
@router.get("/register", response_model=list[dict])
async def list_register(
    status: str | None = Query(default=None, description="pending | attested | rejected"),
    savings_class: str | None = Query(default=None, description="reduction | avoidance"),
    fiscal_year: int | None = Query(default=None),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    await _ensure_seeded(caller)
    wheres: list[str] = []
    params: list = []
    if status:
        wheres.append("status = %s"); params.append(status)
    if savings_class:
        wheres.append("savings_class = %s"); params.append(savings_class)
    if fiscal_year:
        wheres.append("fiscal_year = %s"); params.append(fiscal_year)
    where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""
    async with db_conn(caller) as conn:
        rows = await (await conn.execute(
            f"SELECT {_REGISTER_COLS} FROM savings_register {where_sql} "
            f"ORDER BY submitted_at DESC, savings_amount_usd DESC",
            params,
        )).fetchall()
        return [_row(r) for r in rows]


@router.get("/kpis", response_model=dict)
async def kpis(caller: CallerIdentity = Depends(caller_identity)) -> dict:
    """Headline savings KPIs. Attested savings are framed against addressable spend
    (mv_spend) — no FP&A dependency."""
    await _ensure_seeded(caller)
    s = get_settings()
    attested_total = pending_total = hard = soft = 0.0
    pending_count = 0
    by_quarter: list[dict] = []
    async with db_conn(caller) as conn:
        agg = await (await conn.execute(
            "SELECT status, savings_class, COALESCE(SUM(savings_amount_usd),0), COUNT(*) "
            "FROM savings_register GROUP BY status, savings_class"
        )).fetchall()
        for st, cls, amt, cnt in agg:
            amt = float(amt or 0)
            if st == "attested":
                attested_total += amt
                if cls == "reduction":
                    hard += amt
                else:
                    soft += amt
            elif st == "pending":
                pending_total += amt
                pending_count += int(cnt or 0)
        byq = await (await conn.execute(
            """
            SELECT fiscal_year, fiscal_quarter,
                   SUM(CASE WHEN savings_class='reduction' AND status='attested' THEN savings_amount_usd ELSE 0 END),
                   SUM(CASE WHEN savings_class='avoidance' AND status='attested' THEN savings_amount_usd ELSE 0 END)
            FROM savings_register
            GROUP BY fiscal_year, fiscal_quarter
            ORDER BY fiscal_year, fiscal_quarter
            """
        )).fetchall()
        by_quarter = [
            {"fiscal_year": int(fy), "fiscal_quarter": int(fq), "reduction": float(red or 0), "avoidance": float(avd or 0)}
            for fy, fq, red, avd in byq
        ]

    addr_row = fetch_one(
        caller,
        f"""
        SELECT ROUND(MEASURE(addressable_spend), 2) AS addr
        FROM {s.gold}.mv_spend
        WHERE invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
        GROUP BY ALL
        """,
    ) or {}
    addressable = float(addr_row.get("addr") or 0)

    return {
        "attested_total": attested_total,
        "pending_total": pending_total,
        "pending_count": pending_count,
        "hard_total": hard,
        "soft_total": soft,
        "addressable_spend": addressable,
        "savings_pct_of_addressable": round(attested_total / addressable * 100, 2) if addressable else None,
        "by_quarter": by_quarter,
    }


@router.get("/artifacts", response_model=list[dict])
def search_artifacts(
    q: str = Query(default=""),
    kind: str | None = Query(default=None, description="sourcing_event | contract"),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    """Search sourcing events + contracts to attach a new savings record to."""
    s = get_settings()
    like = f"%{q.lower()}%"
    out: list[dict] = []
    if kind in (None, "sourcing_event"):
        events = fetch_all(
            caller,
            f"""
            SELECT 'sourcing_event' AS artifact_type, source_id AS artifact_id,
                   MAX(event_title) AS title, MAX(supplier_id) AS supplier_id,
                   MAX(supplier_name) AS supplier_name, MAX(segment_code) AS segment_code,
                   MAX(fiscal_year) AS fiscal_year, MAX(fiscal_quarter) AS fiscal_quarter,
                   ROUND(MAX(baseline_amount), 2) AS baseline_amount,
                   ROUND(MAX(awarded_amount), 2)  AS realized_amount
            FROM {s.gold}.fact_cost_savings
            WHERE LOWER(event_title) LIKE ? OR LOWER(supplier_name) LIKE ?
            GROUP BY source_id
            ORDER BY 3
            LIMIT 12
            """,
            [like, like],
        )
        out.extend(events)
    if kind in (None, "contract"):
        contracts = fetch_all(
            caller,
            f"""
            SELECT 'contract' AS artifact_type, c.contract_workspace_id AS artifact_id,
                   c.title, c.supplier_id, sup.supplier_name,
                   CAST(NULL AS STRING) AS segment_code,
                   YEAR(c.effective_date) AS fiscal_year, QUARTER(c.effective_date) AS fiscal_quarter,
                   ROUND(c.total_committed_spend, 2) AS baseline_amount,
                   CAST(NULL AS DOUBLE) AS realized_amount
            FROM {s.silver}.contract_inbound c
            LEFT JOIN {s.gold}.dim_supplier sup ON c.supplier_id = sup.supplier_id
            WHERE c.contract_type IN ('Statement of Work', 'Framework')
              AND c.status = 'Active'
              AND c.effective_date <= CURRENT_DATE()
              AND c.expiration_date >= CURRENT_DATE()
              AND (LOWER(c.title) LIKE ? OR LOWER(sup.supplier_name) LIKE ?)
            ORDER BY c.total_committed_spend DESC
            LIMIT 12
            """,
            [like, like],
        )
        out.extend(contracts)
    return out


@router.post("/register", response_model=dict)
async def submit_savings(
    body: SavingsSubmit,
    caller: CallerIdentity = Depends(caller_identity),
) -> dict:
    """Log a new savings record — lands as 'pending' for a second person to attest."""
    if body.savings_type not in SAVINGS_TYPES:
        raise HTTPException(400, f"savings_type must be one of {sorted(SAVINGS_TYPES)}")
    expected_class = SAVINGS_TYPES[body.savings_type][0]
    if body.savings_class != expected_class:
        raise HTTPException(400, f"savings_type '{body.savings_type}' belongs to class '{expected_class}'")
    if body.artifact_type not in ("sourcing_event", "contract"):
        raise HTTPException(400, "artifact_type must be 'sourcing_event' or 'contract'")
    if body.savings_amount_usd <= 0:
        raise HTTPException(400, "savings_amount_usd must be positive")

    record_id = str(uuid.uuid4())
    now = datetime.utcnow()
    values = (
        record_id, body.artifact_type, body.artifact_id, body.artifact_title,
        body.savings_class, body.savings_type, body.supplier_id, body.supplier_name,
        body.segment_code, body.fiscal_year, body.fiscal_quarter,
        body.baseline_amount_usd, body.realized_amount_usd, body.savings_amount_usd,
        body.baseline_context, body.notes, caller.email, now, "pending", None, None, None,
    )
    async with db_conn(caller) as conn:
        await conn.execute(_INSERT_SQL, values)
        row = await (await conn.execute(
            f"SELECT {_REGISTER_COLS} FROM savings_register WHERE record_id = %s", (record_id,)
        )).fetchone()
        if not row:
            raise HTTPException(500, "Insert succeeded but fetch returned no row")
        return _row(row)


@router.post("/register/{record_id}/attest", response_model=dict)
async def attest_savings(
    record_id: str,
    caller: CallerIdentity = Depends(caller_identity),
) -> dict:
    """Attest a pending record. A second person must attest — you cannot attest
    your own submission (segregation of duties)."""
    now = datetime.utcnow()
    async with db_conn(caller) as conn:
        existing = await (await conn.execute(
            "SELECT submitted_by FROM savings_register WHERE record_id = %s", (record_id,)
        )).fetchone()
        if not existing:
            raise HTTPException(404, f"Savings record {record_id} not found")
        if existing[0] and existing[0].lower() == caller.email.lower():
            raise HTTPException(403, "A different person must attest a submission (segregation of duties).")
        await conn.execute(
            "UPDATE savings_register SET status='attested', attested_by=%s, attested_at=%s, "
            "rejection_reason=NULL WHERE record_id=%s",
            (caller.email, now, record_id),
        )
        row = await (await conn.execute(
            f"SELECT {_REGISTER_COLS} FROM savings_register WHERE record_id = %s", (record_id,)
        )).fetchone()
        return _row(row)


@router.post("/register/{record_id}/reject", response_model=dict)
async def reject_savings(
    record_id: str,
    body: SavingsRejectBody,
    caller: CallerIdentity = Depends(caller_identity),
) -> dict:
    if not body.reason.strip():
        raise HTTPException(400, "reason is required")
    now = datetime.utcnow()
    async with db_conn(caller) as conn:
        await conn.execute(
            "UPDATE savings_register SET status='rejected', attested_by=%s, attested_at=%s, "
            "rejection_reason=%s WHERE record_id=%s",
            (caller.email, now, body.reason.strip(), record_id),
        )
        row = await (await conn.execute(
            f"SELECT {_REGISTER_COLS} FROM savings_register WHERE record_id = %s", (record_id,)
        )).fetchone()
        if not row:
            raise HTTPException(404, f"Savings record {record_id} not found")
        return _row(row)
