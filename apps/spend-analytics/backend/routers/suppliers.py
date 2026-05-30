"""Supplier Performance and Payment-Terms Renegotiation endpoints.

All spend / on-time / DPO metrics filter to `payment_status = 'PAID'` and
are scoped to the trailing 12 months so every column on the scorecard uses
the same denominator. On-time payment is spend-weighted, not line-count
weighted. The `measured_maverick_pct` column replaces the synthetic
`dim_supplier.maverick_propensity` seed with an observed measure: T12M
paid spend that is NOT linked to any active contract for the supplier.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import CallerIdentity, caller_identity
from ..config import get_settings
from ..db import fetch_all

router = APIRouter(prefix="/suppliers", tags=["suppliers"])

# DPO targets by current payment terms bucket (treasury-policy heuristic;
# the renegotiation_targets endpoint surfaces these as the "stretch to"
# number for working-capital opportunity).
_TARGET_DPO: dict[str, int] = {
    "Net15": 45,
    "Net30": 60,
    "Net45": 60,
    "Net60": 60,
}


# Per-supplier T12M scorecard row, sourced from the governed supplier-performance
# metric view (gold.mv_supplier_performance, nested on mv_spend). This is a
# metric-view query (MEASURE + GROUP BY ALL); callers wrap it as a subquery so
# they can filter / sort / derive on the resulting columns with plain SQL.
#
# Ratio measures are stored as fractions (0–1) in the view; we ×100 here to keep
# the legacy percent-number contract. Dimension aliases (region, category_primary,
# is_regulated_supplier) preserve the response keys the frontend already reads.
def _mvsp_inner_sql(s) -> str:
    return f"""
        SELECT
            supplier_id                                   AS supplier_id,
            supplier_name                                 AS supplier_name,
            supplier_region                               AS region,
            supplier_category                             AS category_primary,
            payment_terms                                 AS payment_terms,
            is_regulated                                  AS is_regulated_supplier,
            ROUND(MEASURE(trailing_spend), 2)             AS trailing_12m_spend,
            MEASURE(invoice_count)                        AS invoice_count,
            ROUND(MEASURE(on_time_payment_pct) * 100, 1)  AS on_time_payment_pct,
            ROUND(MEASURE(avg_dpo), 1)                    AS avg_dpo,
            ROUND(MEASURE(measured_maverick_pct) * 100, 1) AS measured_maverick_pct,
            ROUND(MEASURE(managed_spend_pct) * 100, 1)    AS managed_spend_pct
        FROM {s.gold}.mv_supplier_performance
        WHERE invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
        GROUP BY ALL
    """


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
        "measured_maverick_pct", "invoice_count", "supplier_name",
    }
    if sort_by not in allowed_sort:
        raise HTTPException(400, f"sort_by must be one of {sorted(allowed_sort)}")
    if direction.lower() not in {"asc", "desc"}:
        raise HTTPException(400, "direction must be asc or desc")

    s = get_settings()
    wheres: list[str] = []
    params: list = []
    if category:
        wheres.append("category_primary = ?")
        params.append(category)
    if region:
        wheres.append("region = ?")
        params.append(region)
    if exclude_regulated:
        wheres.append("COALESCE(is_regulated_supplier, FALSE) = FALSE")
    where_sql = ("WHERE " + " AND ".join(wheres)) if wheres else ""

    sql = f"""
        SELECT
            supplier_id, supplier_name, region, category_primary, payment_terms,
            is_regulated_supplier, trailing_12m_spend, invoice_count,
            on_time_payment_pct, avg_dpo, measured_maverick_pct
        FROM ({_mvsp_inner_sql(s)})
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
    Regulated suppliers are always excluded. Spend filter restricts to T12M paid invoices."""
    s = get_settings()
    sql = f"""
        SELECT
            supplier_id,
            supplier_name,
            payment_terms                                       AS current_payment_terms,
            avg_dpo                                             AS current_dpo,
            CASE payment_terms
                WHEN 'Net15' THEN 45
                WHEN 'Net30' THEN 60
                WHEN 'Net45' THEN 60
                ELSE              60
            END                                                 AS target_dpo,
            ROUND(
                trailing_12m_spend
                / 365.0
                * GREATEST(
                    0,
                    CASE payment_terms
                        WHEN 'Net15' THEN 45
                        WHEN 'Net30' THEN 60
                        WHEN 'Net45' THEN 60
                        ELSE              60
                    END - COALESCE(avg_dpo, 30)
                ),
                2
            )                                                   AS working_capital_opportunity_usd,
            trailing_12m_spend,
            category_primary
        FROM ({_mvsp_inner_sql(s)})
        WHERE COALESCE(is_regulated_supplier, FALSE) = FALSE
          AND trailing_12m_spend > 100000
          AND payment_terms IN ('Net15', 'Net30', 'Net45')
        ORDER BY working_capital_opportunity_usd DESC
        LIMIT ?
    """
    return fetch_all(caller, sql, [top_n])


@router.get("/{supplier_id}/scorecard", response_model=dict)
def supplier_scorecard(
    supplier_id: str,
    caller: CallerIdentity = Depends(caller_identity),
) -> dict:
    """Single-supplier drilldown. Header and category breakdown are scoped to
    T12M paid invoices; contracts list is filtered to currently effective
    active SOW/Framework rows; spend_trend returns the last 8 quarters."""
    s = get_settings()
    header = fetch_all(
        caller,
        f"""
        SELECT * FROM ({_mvsp_inner_sql(s)})
        WHERE supplier_id = ?
        """,
        [supplier_id],
    )
    if not header:
        raise HTTPException(404, f"Supplier {supplier_id} not found")

    # Category breakdown — T12M paid only (via mv_spend), so it matches header spend.
    category_breakdown = fetch_all(
        caller,
        f"""
        SELECT category_primary AS category, ROUND(MEASURE(total_spend), 2) AS spend_usd
        FROM {s.gold}.mv_spend
        WHERE supplier_id = ?
          AND invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
        GROUP BY ALL
        ORDER BY spend_usd DESC
        """,
        [supplier_id],
    )

    # Active contracts only (status + calendar validity), most-recent first.
    contracts = fetch_all(
        caller,
        f"""
        SELECT contract_workspace_id, contract_type, title, effective_date,
               expiration_date, total_committed_spend, status,
               CASE
                   WHEN total_committed_spend > 0
                   THEN ROUND(actual_spend_to_date / total_committed_spend * 100, 1)
                   ELSE NULL
               END AS pct_consumed,
               DATEDIFF(expiration_date, CURRENT_DATE()) AS days_to_expiration
        FROM {s.silver}.contract_inbound
        WHERE supplier_id = ?
          AND contract_type IN ('Statement of Work', 'Framework')
          AND status = 'Active'
          AND effective_date <= CURRENT_DATE()
          AND expiration_date >= CURRENT_DATE()
        ORDER BY effective_date DESC
        LIMIT 10
        """,
        [supplier_id],
    )

    # Spend trend — last 8 quarters of PAID spend, ascending so the
    # SparklineChart renders left-to-right chronologically.
    spend_trend = fetch_all(
        caller,
        f"""
        WITH q AS (
            SELECT fiscal_year, fiscal_quarter, ROUND(MEASURE(total_spend), 2) AS spend_usd
            FROM {s.gold}.mv_spend
            WHERE supplier_id = ?
            GROUP BY ALL
            ORDER BY fiscal_year DESC, fiscal_quarter DESC
            LIMIT 8
        )
        SELECT fiscal_year, fiscal_quarter, spend_usd
        FROM q
        ORDER BY fiscal_year ASC, fiscal_quarter ASC
        """,
        [supplier_id],
    )

    return {
        **header[0],
        "category_breakdown": category_breakdown,
        "contracts": contracts,
        "spend_trend": spend_trend,
    }
