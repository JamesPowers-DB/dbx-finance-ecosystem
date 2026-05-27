"""Contract Burn-Down, Renewal Monitoring, and Drilldown endpoints.

Every spend aggregate in this router filters to `payment_status = 'PAID'`
and scopes invoices to the contract — both by `supplier_id` AND by the
contract's effective–expiration window — so utilization figures reflect
spend that actually consumed THIS contract, not the supplier's whole book
of business.

"Active" means status = 'Active' AND today falls inside the
effective–expiration window. Status alone is insufficient: source data
can carry Active rows whose dates have already expired.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth import CallerIdentity, caller_identity
from ..config import get_settings
from ..db import fetch_all, fetch_one, t12m_supplier_spend_sql
from ..models import (
    ContractBurnDown,
    ContractInvoiceRow,
    ContractPORow,
    ContractRow,
)

router = APIRouter(prefix="/contracts", tags=["contracts"])

_ALLOWED_SORT = {
    "total_committed_spend", "pct_consumed", "days_to_expiration",
    "trailing_12m_spend", "supplier_name",
}


# CTE returning per-contract T12M paid spend that ACTUALLY fell inside the
# contract's effective–expiration window. Replaces the old supplier-rollup
# join, which over-attributed any supplier invoice to every one of their
# contracts. `pct_consumed` is recomputed here too so list view and
# drilldown chart use the same numbers.
def _contract_scoped_consumption_sql(s) -> str:
    return f"""
        SELECT
            c.contract_workspace_id,
            COALESCE(SUM(i.amount), 0) AS contract_scoped_spend,
            CASE
                WHEN c.total_committed_spend > 0
                THEN ROUND(COALESCE(SUM(i.amount), 0) / c.total_committed_spend * 100, 1)
                ELSE NULL
            END AS pct_consumed
        FROM {s.silver}.contract_inbound c
        LEFT JOIN {s.gold}.fact_invoices i
            ON i.supplier_id = c.supplier_id
           AND i.invoice_date BETWEEN c.effective_date AND c.expiration_date
           AND i.payment_status = 'PAID'
        GROUP BY c.contract_workspace_id, c.total_committed_spend
    """


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
        # Calendar validity — status='Active' alone can include expired rows.
        "c.effective_date <= CURRENT_DATE()",
        "c.expiration_date >= CURRENT_DATE()",
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
            cons.contract_scoped_spend                              AS actual_spend_to_date,
            cons.pct_consumed,
            DATEDIFF(c.expiration_date, CURRENT_DATE())             AS days_to_expiration,
            COALESCE(inv_agg.trailing_12m_spend, 0)                AS trailing_12m_spend,
            c.status,
            c.region
        FROM {s.silver}.contract_inbound c
        LEFT JOIN {s.gold}.dim_supplier s
            ON c.supplier_id = s.supplier_id
        LEFT JOIN ({t12m_supplier_spend_sql(s)}) inv_agg
            ON c.supplier_id = inv_agg.supplier_id
        LEFT JOIN ({_contract_scoped_consumption_sql(s)}) cons
            ON c.contract_workspace_id = cons.contract_workspace_id
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
            cons.contract_scoped_spend                              AS actual_spend_to_date,
            cons.pct_consumed,
            DATEDIFF(c.expiration_date, CURRENT_DATE())             AS days_to_expiration,
            COALESCE(inv_agg.trailing_12m_spend, 0)                AS trailing_12m_spend,
            c.status,
            c.region
        FROM {s.silver}.contract_inbound c
        LEFT JOIN {s.gold}.dim_supplier s
            ON c.supplier_id = s.supplier_id
        LEFT JOIN ({t12m_supplier_spend_sql(s)}) inv_agg
            ON c.supplier_id = inv_agg.supplier_id
        LEFT JOIN ({_contract_scoped_consumption_sql(s)}) cons
            ON c.contract_workspace_id = cons.contract_workspace_id
        WHERE c.contract_type IN ('Statement of Work', 'Framework')
          AND c.status = 'Active'
          AND c.effective_date <= CURRENT_DATE()
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
    """Quarterly cumulative spend for a single contract.

    Scoped to the contract's supplier AND the contract's effective–expiration
    window AND paid invoices only. Replaces the prior implementation, which
    summed ALL invoices for the supplier and overstated utilization wildly
    for any supplier with multiple contracts or off-contract spend.

    Implementation note: the contract scope (supplier + effective window) is
    resolved inside the SQL via a CTE, so only `contract_id` (a string) is
    bound as a query parameter. We previously bound `datetime.date` objects
    via qmark `?` markers — that pattern is not reliably supported across
    databricks-sql-connector versions and caused the endpoint to 500 on the
    deployed runtime, leaving the drilldown panel stuck on "Loading…".
    """
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
        WITH c AS (
            SELECT supplier_id, effective_date, expiration_date
            FROM {s.silver}.contract_inbound
            WHERE contract_workspace_id = ?
        )
        SELECT
            CONCAT('FY', i.fiscal_year % 100, ' Q', i.fiscal_quarter)    AS period,
            SUM(i.amount)                                                 AS period_spend,
            SUM(SUM(i.amount)) OVER (
                ORDER BY i.fiscal_year, i.fiscal_quarter
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            )                                                             AS cumulative_spend
        FROM {s.gold}.fact_invoices i
        JOIN c
          ON i.supplier_id = c.supplier_id
         AND i.invoice_date BETWEEN c.effective_date AND c.expiration_date
        WHERE i.payment_status = 'PAID'
        GROUP BY i.fiscal_year, i.fiscal_quarter
        ORDER BY i.fiscal_year, i.fiscal_quarter
        """,
        [contract_id],
    )

    # `total_committed_spend` comes back from DBSQL as decimal.Decimal — coerce
    # to float once so the percentage arithmetic below doesn't blow up with
    # `TypeError: unsupported operand type(s) for /: 'float' and 'decimal.Decimal'`.
    committed = float(header.get("total_committed_spend") or 0)
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


@router.get("/{contract_id}/invoices", response_model=list[ContractInvoiceRow])
def contract_invoices(
    contract_id: str,
    limit: int = Query(default=100, le=500),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    """Linked invoices tab — invoices that consumed THIS contract.

    Uses the same scope as burn_down (supplier + contract date window +
    paid) so the totals reconcile with the drilldown chart. Scope is
    resolved server-side via a CTE so only `contract_id` and `limit` are
    bound — see contract_burn_down docstring for the date-binding caveat.
    """
    s = get_settings()
    # Cheap existence check just to preserve the 404 contract-not-found
    # response; the real query joins via the CTE below.
    exists = fetch_one(
        caller,
        f"SELECT 1 FROM {s.silver}.contract_inbound WHERE contract_workspace_id = ?",
        [contract_id],
    )
    if not exists:
        from fastapi import HTTPException
        raise HTTPException(404, f"Contract {contract_id} not found")

    rows = fetch_all(
        caller,
        f"""
        WITH c AS (
            SELECT supplier_id, effective_date, expiration_date
            FROM {s.silver}.contract_inbound
            WHERE contract_workspace_id = ?
        )
        SELECT
            -- fact_invoices.invoice_line_id is BIGINT in UC; cast to STRING so
            -- pydantic's ContractInvoiceRow.invoice_line_id: str accepts it.
            CAST(i.invoice_line_id AS STRING) AS invoice_line_id,
            i.invoice_date, i.amount,
            i.true_category_primary, i.payment_status
        FROM {s.gold}.fact_invoices i
        JOIN c
          ON i.supplier_id = c.supplier_id
         AND i.invoice_date BETWEEN c.effective_date AND c.expiration_date
        WHERE i.payment_status = 'PAID'
        ORDER BY i.invoice_date DESC, i.amount DESC
        LIMIT ?
        """,
        [contract_id, limit],
    )
    return rows


@router.get("/{contract_id}/purchase_orders", response_model=list[ContractPORow])
def contract_purchase_orders(
    contract_id: str,
    limit: int = Query(default=100, le=500),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    """Linked POs tab — POs against THIS supplier in the contract window.

    A PO issued before/after the contract is not consuming this contract,
    so we scope by both `supplier_id` AND `po_created_date BETWEEN
    effective_date AND expiration_date`. Same CTE pattern as burn_down /
    invoices to avoid binding date parameters via qmark.
    """
    s = get_settings()
    exists = fetch_one(
        caller,
        f"SELECT 1 FROM {s.silver}.contract_inbound WHERE contract_workspace_id = ?",
        [contract_id],
    )
    if not exists:
        from fastapi import HTTPException
        raise HTTPException(404, f"Contract {contract_id} not found")

    rows = fetch_all(
        caller,
        f"""
        WITH c AS (
            SELECT supplier_id, effective_date, expiration_date
            FROM {s.silver}.contract_inbound
            WHERE contract_workspace_id = ?
        )
        SELECT p.po_number, p.po_line_num, p.extended_amount, p.true_category_primary
        FROM {s.gold}.fact_purchase_orders p
        JOIN c
          ON p.supplier_id = c.supplier_id
         AND p.po_created_date BETWEEN c.effective_date AND c.expiration_date
        ORDER BY p.extended_amount DESC NULLS LAST
        LIMIT ?
        """,
        [contract_id, limit],
    )
    return rows
