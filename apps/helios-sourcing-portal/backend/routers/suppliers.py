"""Supplier Performance and Payment-Terms Renegotiation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth import CallerIdentity, caller_identity
from ..config import get_settings
from ..db import fetch_all

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

# DPO targets by current payment terms bucket
_TARGET_DPO: dict[str, int] = {
    "Net15": 45,
    "Net30": 60,
    "Net45": 60,
    "Net60": 60,
}


@router.get("", response_model=list[dict])
def list_suppliers(
    category: str | None = Query(default=None),
    region: str | None = Query(default=None),
    exclude_regulated: bool = Query(default=False),
    sort_by: str = Query(default="trailing_12m_spend"),
    direction: str = Query(default="desc"),
    limit: int = Query(default=200, le=500),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    allowed_sort = {
        "trailing_12m_spend", "on_time_payment_pct", "avg_dpo",
        "maverick_propensity", "invoice_count", "supplier_name",
    }
    if sort_by not in allowed_sort:
        from fastapi import HTTPException
        raise HTTPException(400, f"sort_by must be one of {sorted(allowed_sort)}")
    if direction.lower() not in {"asc", "desc"}:
        from fastapi import HTTPException
        raise HTTPException(400, "direction must be asc or desc")

    s = get_settings()
    wheres: list[str] = []
    params: list = []
    if category:
        wheres.append("s.category_primary = ?")
        params.append(category)
    if region:
        wheres.append("s.region = ?")
        params.append(region)
    if exclude_regulated:
        wheres.append("COALESCE(s.is_regulated_supplier, FALSE) = FALSE")
    where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""

    sql = f"""
        SELECT
            s.supplier_id,
            s.supplier_name,
            s.region,
            s.category_primary,
            s.payment_terms,
            s.maverick_propensity,
            s.is_regulated_supplier,
            agg.trailing_12m_spend,
            agg.invoice_count,
            agg.on_time_payment_pct,
            agg.avg_dpo
        FROM {s.gold}.dim_supplier s
        LEFT JOIN (
            SELECT
                supplier_id,
                ROUND(SUM(CASE WHEN invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
                          THEN amount ELSE 0 END), 2)                               AS trailing_12m_spend,
                COUNT(*)                                                             AS invoice_count,
                ROUND(100.0 * SUM(CASE WHEN is_on_time_payment THEN 1 ELSE 0 END)
                      / NULLIF(COUNT(*), 0), 1)                                     AS on_time_payment_pct,
                ROUND(AVG(days_to_pay), 1)                                          AS avg_dpo
            FROM {s.gold}.fact_invoices
            GROUP BY supplier_id
        ) agg
            ON s.supplier_id = agg.supplier_id
        {where_sql}
        ORDER BY {sort_by} {direction.upper()} NULLS LAST
        LIMIT ?
    """
    params.append(limit)
    return fetch_all(caller, sql, params)


@router.get("/renegotiation_targets", response_model=list[dict])
def renegotiation_targets(
    top_n: int = Query(default=25, le=100),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    """Top suppliers ranked by working-capital opportunity from payment-terms extension.
    Regulated suppliers are always excluded."""
    s = get_settings()
    sql = f"""
        WITH agg AS (
            SELECT
                supplier_id,
                ROUND(SUM(amount), 2)                           AS trailing_12m_spend,
                ROUND(AVG(days_to_pay), 1)                      AS current_dpo
            FROM {s.gold}.fact_invoices
            WHERE invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
            GROUP BY supplier_id
        )
        SELECT
            s.supplier_id,
            s.supplier_name,
            s.payment_terms                                     AS current_payment_terms,
            agg.current_dpo,
            CASE s.payment_terms
                WHEN 'Net15' THEN 45
                WHEN 'Net30' THEN 60
                WHEN 'Net45' THEN 60
                ELSE              60
            END                                                 AS target_dpo,
            ROUND(
                agg.trailing_12m_spend
                / 365.0
                * GREATEST(
                    0,
                    CASE s.payment_terms
                        WHEN 'Net15' THEN 45
                        WHEN 'Net30' THEN 60
                        WHEN 'Net45' THEN 60
                        ELSE              60
                    END - COALESCE(agg.current_dpo, 30)
                ),
                2
            )                                                   AS working_capital_opportunity_usd,
            agg.trailing_12m_spend,
            s.category_primary
        FROM {s.gold}.dim_supplier s
        JOIN agg ON s.supplier_id = agg.supplier_id
        WHERE COALESCE(s.is_regulated_supplier, FALSE) = FALSE
          AND agg.trailing_12m_spend > 100000
          AND s.payment_terms IN ('Net15', 'Net30', 'Net45')
        ORDER BY working_capital_opportunity_usd DESC
        LIMIT ?
    """
    return fetch_all(caller, sql, [top_n])


@router.get("/{supplier_id}/scorecard", response_model=dict)
def supplier_scorecard(
    supplier_id: str,
    caller: CallerIdentity = Depends(caller_identity),
) -> dict:
    s = get_settings()
    header = fetch_all(
        caller,
        f"""
        SELECT
            s.supplier_id, s.supplier_name, s.region, s.country_code,
            s.category_primary, s.payment_terms, s.maverick_propensity,
            s.is_regulated_supplier,
            agg.trailing_12m_spend, agg.invoice_count,
            agg.on_time_payment_pct, agg.avg_dpo
        FROM {s.gold}.dim_supplier s
        LEFT JOIN (
            SELECT supplier_id,
                ROUND(SUM(CASE WHEN invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
                          THEN amount ELSE 0 END), 2)  AS trailing_12m_spend,
                COUNT(*)                                AS invoice_count,
                ROUND(100.0 * SUM(CASE WHEN is_on_time_payment THEN 1 ELSE 0 END)
                      / NULLIF(COUNT(*), 0), 1)         AS on_time_payment_pct,
                ROUND(AVG(days_to_pay), 1)              AS avg_dpo
            FROM {s.gold}.fact_invoices
            GROUP BY supplier_id
        ) agg ON s.supplier_id = agg.supplier_id
        WHERE s.supplier_id = ?
        """,
        [supplier_id],
    )
    if not header:
        from fastapi import HTTPException
        raise HTTPException(404, f"Supplier {supplier_id} not found")

    category_breakdown = fetch_all(
        caller,
        f"""
        SELECT true_category_primary AS category, SUM(amount) AS spend_usd
        FROM {s.gold}.fact_invoices
        WHERE supplier_id = ?
        GROUP BY true_category_primary
        ORDER BY spend_usd DESC
        """,
        [supplier_id],
    )
    contracts = fetch_all(
        caller,
        f"""
        SELECT contract_workspace_id, contract_type, title, effective_date,
               expiration_date, total_committed_spend, status
        FROM {s.silver}.contract_inbound
        WHERE supplier_id = ?
          AND contract_type IN ('Statement of Work', 'Framework')
        ORDER BY effective_date DESC
        LIMIT 10
        """,
        [supplier_id],
    )
    return {**header[0], "category_breakdown": category_breakdown, "contracts": contracts}
