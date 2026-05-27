"""Cost Savings Tracking endpoints.

Auto-detected reductions come from gold.fact_cost_savings (SQL MV) and are
read-only. Manual avoidance entries live in Lakebase
(`savings_avoidance_entries`) and flow through an approval workflow:

    submit (approved=false)   →   approve  (approved=true,  approved_at)
                              →   reject   (approved=false, rejected_at)

Only `approved=true` rows are counted in the executive summary so unvetted
attestations do not inflate KPIs. Pending amounts are surfaced separately
as `pending_avoidance_usd` for transparency.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import CallerIdentity, caller_identity
from ..config import get_settings
from ..db import fetch_all
from ..lakebase import db_conn
from ..models import (
    AvoidanceEntry,
    AvoidanceEntryCreate,
    AvoidanceRejectBody,
    CostReductionRow,
    SavingsSummaryRow,
)

router = APIRouter(prefix="/cost_savings", tags=["cost_savings"])


# Explicit column list — never SELECT * from a Lakebase ledger that backs
# an API contract. Order must match the AvoidanceEntry pydantic model.
_AVOIDANCE_COLS = (
    "entry_id, source_type, source_id, segment_code, fiscal_year, "
    "fiscal_quarter, category_primary, supplier_id, supplier_name, "
    "savings_amount_usd, baseline_context, notes, attested_by, attested_at, "
    "approved, approved_by, approved_at, rejected_at, rejection_reason"
)
_AVOIDANCE_COL_NAMES = [c.strip() for c in _AVOIDANCE_COLS.split(",")]


def _row_to_entry(row: tuple) -> dict:
    return dict(zip(_AVOIDANCE_COL_NAMES, row))


@router.get("/reductions", response_model=list[CostReductionRow])
def list_reductions(
    fiscal_year: int | None = Query(default=None),
    fiscal_quarter: int | None = Query(default=None),
    segment_code: str | None = Query(default=None),
    category: str | None = Query(default=None),
    limit: int = Query(default=500, le=2000),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    s = get_settings()
    wheres: list[str] = []
    params: list = []
    if fiscal_year:
        wheres.append("fiscal_year = ?")
        params.append(fiscal_year)
    if fiscal_quarter:
        wheres.append("fiscal_quarter = ?")
        params.append(fiscal_quarter)
    if segment_code:
        wheres.append("segment_code = ?")
        params.append(segment_code)
    if category:
        wheres.append("category_primary = ?")
        params.append(category)
    where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""

    sql = f"""
        SELECT
            savings_event_id, source_type, source_id, segment_code,
            fiscal_year, fiscal_quarter, category_primary,
            supplier_id, supplier_name, event_type, event_title,
            awarded_amount, baseline_amount, savings_amount_usd, savings_rate
        FROM {s.gold}.fact_cost_savings
        {where_sql}
        ORDER BY savings_amount_usd DESC
        LIMIT ?
    """
    params.append(limit)
    return fetch_all(caller, sql, params)


@router.get("/avoidance", response_model=list[AvoidanceEntry])
async def list_avoidance(
    fiscal_year: int | None = Query(default=None),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    async with db_conn(caller) as conn:
        wheres = []
        params: list = []
        if fiscal_year:
            wheres.append("fiscal_year = %s")
            params.append(fiscal_year)
        where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""
        rows = await conn.execute(
            f"SELECT {_AVOIDANCE_COLS} FROM savings_avoidance_entries "
            f"{where_sql} ORDER BY attested_at DESC",
            params,
        )
        return [_row_to_entry(row) for row in await rows.fetchall()]


@router.post("/avoidance", response_model=AvoidanceEntry)
async def create_avoidance(
    body: AvoidanceEntryCreate,
    caller: CallerIdentity = Depends(caller_identity),
) -> dict:
    """Log a manual cost-avoidance entry. Requires attestation (the caller's email).

    Entries land with `approved=False` and are excluded from the executive
    summary until a reviewer approves them.
    """
    if body.savings_amount_usd <= 0:
        raise HTTPException(400, "savings_amount_usd must be positive")
    entry_id = str(uuid.uuid4())
    now = datetime.utcnow()
    async with db_conn(caller) as conn:
        await conn.execute(
            """
            INSERT INTO savings_avoidance_entries (
                entry_id, source_type, source_id, segment_code,
                fiscal_year, fiscal_quarter, category_primary,
                supplier_id, supplier_name, savings_amount_usd,
                baseline_context, notes, attested_by, attested_at, approved
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                entry_id, body.source_type, body.source_id, body.segment_code,
                body.fiscal_year, body.fiscal_quarter, body.category_primary,
                body.supplier_id, body.supplier_name, body.savings_amount_usd,
                body.baseline_context, body.notes, caller.email, now, False,
            ),
        )
        row = await (await conn.execute(
            f"SELECT {_AVOIDANCE_COLS} FROM savings_avoidance_entries WHERE entry_id = %s",
            (entry_id,),
        )).fetchone()
        if not row:
            raise HTTPException(500, "Insert succeeded but fetch returned no row")
        return _row_to_entry(row)


@router.post("/avoidance/{entry_id}/approve", response_model=AvoidanceEntry)
async def approve_avoidance(
    entry_id: str,
    caller: CallerIdentity = Depends(caller_identity),
) -> dict:
    """Mark an avoidance entry as approved. Approved entries flow into the
    executive savings summary; unapproved entries do not."""
    now = datetime.utcnow()
    async with db_conn(caller) as conn:
        await conn.execute(
            """
            UPDATE savings_avoidance_entries
               SET approved        = TRUE,
                   approved_by     = %s,
                   approved_at     = %s,
                   rejected_at     = NULL,
                   rejection_reason = NULL
             WHERE entry_id = %s
            """,
            (caller.email, now, entry_id),
        )
        row = await (await conn.execute(
            f"SELECT {_AVOIDANCE_COLS} FROM savings_avoidance_entries WHERE entry_id = %s",
            (entry_id,),
        )).fetchone()
        if not row:
            raise HTTPException(404, f"Avoidance entry {entry_id} not found")
        return _row_to_entry(row)


@router.post("/avoidance/{entry_id}/reject", response_model=AvoidanceEntry)
async def reject_avoidance(
    entry_id: str,
    body: AvoidanceRejectBody,
    caller: CallerIdentity = Depends(caller_identity),
) -> dict:
    """Reject an avoidance entry with a reason. Excluded from summary totals."""
    if not body.reason.strip():
        raise HTTPException(400, "reason is required")
    now = datetime.utcnow()
    async with db_conn(caller) as conn:
        await conn.execute(
            """
            UPDATE savings_avoidance_entries
               SET approved         = FALSE,
                   approved_by      = %s,
                   approved_at      = NULL,
                   rejected_at      = %s,
                   rejection_reason = %s
             WHERE entry_id = %s
            """,
            (caller.email, now, body.reason.strip(), entry_id),
        )
        row = await (await conn.execute(
            f"SELECT {_AVOIDANCE_COLS} FROM savings_avoidance_entries WHERE entry_id = %s",
            (entry_id,),
        )).fetchone()
        if not row:
            raise HTTPException(404, f"Avoidance entry {entry_id} not found")
        return _row_to_entry(row)


@router.get("/summary", response_model=list[SavingsSummaryRow])
async def savings_summary(
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    """Join auto-detected reductions + APPROVED manual avoidance + FP&A budget.

    Pending (unapproved) avoidance is surfaced as a separate column so it
    is visible without inflating the headline savings number. The result is
    a full-outer join over (segment, fiscal_year, fiscal_quarter) so quarters
    with avoidance-only OR reduction-only entries still appear.
    """
    s = get_settings()
    reductions = fetch_all(
        caller,
        f"""
        SELECT
            COALESCE(segment_code, 'Unknown')   AS segment_code,
            fiscal_year, fiscal_quarter,
            SUM(savings_amount_usd)             AS reduction_usd
        FROM {s.gold}.fact_cost_savings
        GROUP BY segment_code, fiscal_year, fiscal_quarter
        """,
    )
    # Operating-expense budget = COGS + SGA. The schema does not carry an
    # 'EXPENSE' account_type; filtering on that returns zero rows and the
    # savings_pct_of_budget column collapses to null.
    budgets = fetch_all(
        caller,
        f"""
        SELECT segment_code, fiscal_year, fiscal_quarter,
               SUM(amount_usd) AS fpa_budget_usd
        FROM {s.gold}.fact_fpa_budgets
        WHERE account_type IN ('COGS', 'SGA')
        GROUP BY segment_code, fiscal_year, fiscal_quarter
        """,
    )

    # Fetch approved + pending avoidance from Lakebase. Best-effort: if the
    # Lakebase connection fails we still return reductions, but we tag the
    # result so the UI can warn.
    approved_by_key: dict[tuple, float] = {}
    pending_by_key: dict[tuple, float] = {}
    try:
        async with db_conn(caller) as conn:
            rows = await (await conn.execute(
                """
                SELECT COALESCE(segment_code,'Unknown'), fiscal_year, fiscal_quarter,
                       SUM(CASE WHEN approved THEN savings_amount_usd ELSE 0 END)
                           AS approved_usd,
                       SUM(CASE WHEN NOT approved AND rejected_at IS NULL
                                THEN savings_amount_usd ELSE 0 END)
                           AS pending_usd
                FROM savings_avoidance_entries
                GROUP BY 1,2,3
                """
            )).fetchall()
            for seg, fy, fq, app_amt, pen_amt in rows:
                approved_by_key[(seg, fy, fq)] = float(app_amt or 0)
                pending_by_key[(seg, fy, fq)] = float(pen_amt or 0)
    except Exception:
        # Lakebase down — leave both dicts empty. The summary still renders
        # with reductions-only data; the UI can detect 0 pending/approved
        # across all rows as a hint.
        pass

    budget_by_key = {
        (r["segment_code"], r["fiscal_year"], r["fiscal_quarter"]): float(r["fpa_budget_usd"] or 0)
        for r in budgets
    }
    reduction_by_key = {
        (r["segment_code"], r["fiscal_year"], r["fiscal_quarter"]): float(r["reduction_usd"] or 0)
        for r in reductions
    }

    # Full outer join over the union of all keys so periods with only
    # avoidance (no auto-detected reductions) still appear.
    all_keys = set(reduction_by_key) | set(approved_by_key) | set(pending_by_key)

    result = []
    for key in all_keys:
        seg, fy, fq = key
        red = reduction_by_key.get(key, 0.0)
        approved = approved_by_key.get(key, 0.0)
        pending = pending_by_key.get(key, 0.0)
        # Headline total = reductions + APPROVED avoidance. Pending stays out.
        total = red + approved
        budget = budget_by_key.get(key)
        result.append({
            "segment_code": seg,
            "fiscal_year": fy,
            "fiscal_quarter": fq,
            "reduction_usd": red,
            "avoidance_usd": approved,
            "pending_avoidance_usd": pending,
            "total_savings_usd": total,
            "fpa_budget_usd": budget,
            "savings_pct_of_budget": round(total / budget * 100, 2) if budget else None,
        })
    return sorted(result, key=lambda x: (x["fiscal_year"], x["fiscal_quarter"], x["segment_code"]))
