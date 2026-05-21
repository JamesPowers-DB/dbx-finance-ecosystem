"""Contract Burn-Down and Renewal Monitoring endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth import CallerIdentity, caller_identity
from ..config import get_settings
from ..db import fetch_all, fetch_one
from ..models import ContractBurnDown, ContractRow

router = APIRouter(prefix="/contracts", tags=["contracts"])

_ALLOWED_SORT = {
    "total_committed_spend", "pct_consumed", "days_to_expiration",
    "trailing_12m_spend", "supplier_name",
}


@router.get("", response_model=list[ContractRow])
def list_contracts(
    contract_type: str | None = Query(default=None, description="Filter: 'Statement of Work' or 'Framework'"),
    region: str | None = Query(default=None),
    sort_by: str = Query(default="total_committed_spend"),
    direction: str = Query(default="desc"),
    limit: int = Query(default=200, le=500),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    if sort_by not in _ALLOWED_SORT:
        from fastapi import HTTPException
        raise HTTPException(400, f"sort_by must be one of {sorted(_ALLOWED_SORT)}")
    if direction.lower() not in {"asc", "desc"}:
        from fastapi import HTTPException
        raise HTTPException(400, "direction must be asc or desc")

    s = get_settings()
    wheres = [
        "c.contract_type IN ('Statement of Work', 'Framework')",
        "c.status = 'Active'",
    ]
    params: list = []
    if contract_type:
        wheres.append("c.contract_type = ?")
        params.append(contract_type)
    if region:
        wheres.append("c.region = ?")
        params.append(region)
    where_sql = "WHERE " + " AND ".join(wheres)

    sql = f"""
        SELECT
            c.contract_workspace_id,
            c.contract_type,
            c.title,
            c.supplier_id,
            s.supplier_name,
            c.effective_date,
            c.expiration_date,
            c.total_committed_spend,
            c.actual_spend_to_date,
            CASE
                WHEN c.total_committed_spend > 0
                THEN ROUND(c.actual_spend_to_date / c.total_committed_spend * 100, 1)
                ELSE NULL
            END                                                         AS pct_consumed,
            DATEDIFF(c.expiration_date, CURRENT_DATE())                AS days_to_expiration,
            COALESCE(inv_agg.trailing_12m_spend, 0)                   AS trailing_12m_spend,
            c.status,
            c.region
        FROM {s.silver}.contract_inbound c
        LEFT JOIN {s.gold}.dim_supplier s
            ON c.supplier_id = s.supplier_id
        LEFT JOIN (
            SELECT supplier_id, SUM(amount) AS trailing_12m_spend
            FROM {s.gold}.fact_invoices
            WHERE invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
            GROUP BY supplier_id
        ) inv_agg
            ON c.supplier_id = inv_agg.supplier_id
        {where_sql}
        ORDER BY {sort_by} {direction.upper()} NULLS LAST
        LIMIT ?
    """
    params.append(limit)
    return fetch_all(caller, sql, params)


@router.get("/renewals", response_model=list[ContractRow])
def renewal_queue(
    days_out: int = Query(default=180, le=365),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    """Contracts expiring within `days_out` days, sorted by trailing 12m spend desc."""
    s = get_settings()
    sql = f"""
        SELECT
            c.contract_workspace_id,
            c.contract_type,
            c.title,
            c.supplier_id,
            s.supplier_name,
            c.effective_date,
            c.expiration_date,
            c.total_committed_spend,
            c.actual_spend_to_date,
            CASE
                WHEN c.total_committed_spend > 0
                THEN ROUND(c.actual_spend_to_date / c.total_committed_spend * 100, 1)
                ELSE NULL
            END                                                         AS pct_consumed,
            DATEDIFF(c.expiration_date, CURRENT_DATE())                AS days_to_expiration,
            COALESCE(inv_agg.trailing_12m_spend, 0)                   AS trailing_12m_spend,
            c.status,
            c.region
        FROM {s.silver}.contract_inbound c
        LEFT JOIN {s.gold}.dim_supplier s
            ON c.supplier_id = s.supplier_id
        LEFT JOIN (
            SELECT supplier_id, SUM(amount) AS trailing_12m_spend
            FROM {s.gold}.fact_invoices
            WHERE invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
            GROUP BY supplier_id
        ) inv_agg
            ON c.supplier_id = inv_agg.supplier_id
        WHERE c.contract_type IN ('Statement of Work', 'Framework')
          AND c.status = 'Active'
          AND c.expiration_date BETWEEN CURRENT_DATE() AND DATE_ADD(CURRENT_DATE(), ?)
        ORDER BY trailing_12m_spend DESC NULLS LAST
        LIMIT 100
    """
    return fetch_all(caller, sql, [days_out])


@router.get("/{contract_id}/burn_down", response_model=ContractBurnDown)
def contract_burn_down(
    contract_id: str,
    caller: CallerIdentity = Depends(caller_identity),
) -> dict:
    s = get_settings()
    header = fetch_one(
        caller,
        f"""
        SELECT contract_workspace_id, title, total_committed_spend
        FROM {s.silver}.contract_inbound
        WHERE contract_workspace_id = ?
        """,
        [contract_id],
    )
    if not header:
        from fastapi import HTTPException
        raise HTTPException(404, f"Contract {contract_id} not found")

    points = fetch_all(
        caller,
        f"""
        SELECT
            CONCAT('FY', fiscal_year MOD 100, ' Q', fiscal_quarter)    AS period,
            SUM(amount)                                                 AS period_spend,
            SUM(SUM(amount)) OVER (
                ORDER BY fiscal_year, fiscal_quarter
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            )                                                           AS cumulative_spend
        FROM {s.gold}.fact_invoices
        WHERE supplier_id = (
            SELECT supplier_id FROM {s.silver}.contract_inbound
            WHERE contract_workspace_id = ?
        )
        GROUP BY fiscal_year, fiscal_quarter
        ORDER BY fiscal_year, fiscal_quarter
        """,
        [contract_id],
    )

    committed = header.get("total_committed_spend") or 0
    result_points = []
    for p in points:
        cum = float(p.get("cumulative_spend") or 0)
        result_points.append({
            "period": p["period"],
            "cumulative_spend": cum,
            "committed_pct": round(cum / committed * 100, 1) if committed else 0.0,
        })

    return {
        "contract_workspace_id": contract_id,
        "title": header.get("title"),
        "total_committed_spend": committed or None,
        "points": result_points,
    }
