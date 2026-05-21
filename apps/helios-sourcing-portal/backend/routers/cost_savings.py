"""Cost Savings Tracking endpoints.

Auto-detected reductions come from gold.fact_cost_savings (SQL MV).
Manual avoidance entries are stored in Lakebase and joined here.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import CallerIdentity, caller_identity
from ..config import get_settings
from ..db import fetch_all
from ..lakebase import db_conn
from ..models import AvoidanceEntry, AvoidanceEntryCreate, CostReductionRow, SavingsSummaryRow

router = APIRouter(prefix="/cost_savings", tags=["cost_savings"])


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
            f"SELECT * FROM savings_avoidance_entries {where_sql} ORDER BY attested_at DESC",
            params,
        )
        cols = [d.name for d in rows.description] if rows.description else []
        return [dict(zip(cols, row)) for row in await rows.fetchall()]


@router.post("/avoidance", response_model=AvoidanceEntry)
async def create_avoidance(
    body: AvoidanceEntryCreate,
    caller: CallerIdentity = Depends(caller_identity),
) -> dict:
    """Log a manual cost-avoidance entry. Requires attestation (the caller's email)."""
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
            "SELECT * FROM savings_avoidance_entries WHERE entry_id = %s", (entry_id,)
        )).fetchone()
        cols = ["entry_id","source_type","source_id","segment_code","fiscal_year",
                "fiscal_quarter","category_primary","supplier_id","supplier_name",
                "savings_amount_usd","baseline_context","notes","attested_by",
                "attested_at","approved"]
        return dict(zip(cols, row))  # type: ignore[arg-type]


@router.get("/summary", response_model=list[SavingsSummaryRow])
async def savings_summary(
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    """Join auto-detected reductions + manual avoidance + FP&A budget."""
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
    budgets = fetch_all(
        caller,
        f"""
        SELECT segment_code, fiscal_year, fiscal_quarter,
               SUM(amount_usd) AS fpa_budget_usd
        FROM {s.gold}.fact_fpa_budgets
        WHERE account_type = 'EXPENSE'
        GROUP BY segment_code, fiscal_year, fiscal_quarter
        """,
    )

    # Fetch avoidance from Lakebase (best-effort — returns [] if not configured)
    avoidance_by_key: dict[tuple, float] = {}
    try:
        async with db_conn(caller) as conn:
            rows = await (await conn.execute(
                """
                SELECT COALESCE(segment_code,'Unknown'), fiscal_year, fiscal_quarter,
                       SUM(savings_amount_usd)
                FROM savings_avoidance_entries
                GROUP BY 1,2,3
                """
            )).fetchall()
            for seg, fy, fq, amt in rows:
                avoidance_by_key[(seg, fy, fq)] = float(amt or 0)
    except Exception:
        pass

    budget_by_key = {
        (r["segment_code"], r["fiscal_year"], r["fiscal_quarter"]): float(r["fpa_budget_usd"] or 0)
        for r in budgets
    }

    result = []
    for r in reductions:
        key = (r["segment_code"], r["fiscal_year"], r["fiscal_quarter"])
        red = float(r["reduction_usd"] or 0)
        avoid = avoidance_by_key.get(key, 0.0)
        total = red + avoid
        budget = budget_by_key.get(key)
        result.append({
            "segment_code": r["segment_code"],
            "fiscal_year": r["fiscal_year"],
            "fiscal_quarter": r["fiscal_quarter"],
            "reduction_usd": red,
            "avoidance_usd": avoid,
            "total_savings_usd": total,
            "fpa_budget_usd": budget,
            "savings_pct_of_budget": round(total / budget * 100, 2) if budget else None,
        })
    return sorted(result, key=lambda x: (x["fiscal_year"], x["fiscal_quarter"], x["segment_code"]))
