"""Supplier Performance and Payment-Terms Renegotiation endpoints.

All spend / on-time / DPO metrics filter to `payment_status = 'PAID'` and
are scoped to the trailing 12 months so every column on the scorecard uses
the same denominator. On-time payment is spend-weighted, not line-count
weighted. The `measured_maverick_pct` column replaces the synthetic
`dim_supplier.maverick_propensity` seed with an observed measure: T12M
paid spend that is NOT linked to any active contract for the supplier.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth import CallerIdentity, caller_identity
from ..config import get_settings
from ..db import fetch_all, fetch_one

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


# Reusable T12M paid-invoice aggregate per supplier. Carries spend, invoice
# count, spend-weighted on-time payment %, average DPO, and the spend share
# NOT matched to an active contract (= measured maverick %).
#
# Every scorecard column uses the same WHERE predicate so the row reads
# consistently. The contract match join is LEFT JOIN with a supplier-level
# "has any active contract that covers this invoice's date" check.
def _supplier_t12m_agg_sql(s) -> str:
    return f"""
        WITH inv AS (
            SELECT
                i.supplier_id,
                i.invoice_date,
                i.amount,
                i.is_on_time_payment,
                i.days_to_pay,
                -- An invoice line is "contract-matched" if there exists an
                -- active SOW/Framework contract for this supplier whose
                -- effective–expiration window contains the invoice date.
                CASE WHEN EXISTS (
                    SELECT 1 FROM {s.silver}.contract_inbound c
                    WHERE c.supplier_id = i.supplier_id
                      AND c.status = 'Active'
                      AND c.contract_type IN ('Statement of Work', 'Framework')
                      AND i.invoice_date BETWEEN c.effective_date AND c.expiration_date
                ) THEN 1 ELSE 0 END AS is_contract_matched
            FROM {s.gold}.fact_invoices i
            WHERE i.invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
              AND i.payment_status = 'PAID'
        )
        SELECT
            supplier_id,
            ROUND(SUM(amount), 2)                                              AS trailing_12m_spend,
            COUNT(*)                                                            AS invoice_count,
            ROUND(100.0 * SUM(CASE WHEN is_on_time_payment THEN amount ELSE 0 END)
                  / NULLIF(SUM(amount), 0), 1)                                  AS on_time_payment_pct,
            ROUND(AVG(days_to_pay), 1)                                         AS avg_dpo,
            ROUND(100.0 * SUM(CASE WHEN is_contract_matched = 0 THEN amount ELSE 0 END)
                  / NULLIF(SUM(amount), 0), 1)                                  AS measured_maverick_pct
        FROM inv
        GROUP BY supplier_id
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
            s.is_regulated_supplier,
            agg.trailing_12m_spend,
            agg.invoice_count,
            agg.on_time_payment_pct,
            agg.avg_dpo,
            agg.measured_maverick_pct
        FROM {s.gold}.dim_supplier s
        LEFT JOIN ({_supplier_t12m_agg_sql(s)}) agg
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
    Regulated suppliers are always excluded. Spend filter restricts to T12M paid invoices."""
    s = get_settings()
    sql = f"""
        WITH agg AS (
            SELECT
                supplier_id,
                ROUND(SUM(amount), 2)                           AS trailing_12m_spend,
                ROUND(AVG(days_to_pay), 1)                      AS current_dpo
            FROM {s.gold}.fact_invoices
            WHERE invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
              AND payment_status = 'PAID'
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
    """Single-supplier drilldown. Header and category breakdown are scoped to
    T12M paid invoices; contracts list is filtered to currently effective
    active SOW/Framework rows; spend_trend returns the last 8 quarters."""
    s = get_settings()
    header = fetch_all(
        caller,
        f"""
        SELECT
            s.supplier_id, s.supplier_name, s.region, s.country_code,
            s.category_primary, s.payment_terms, s.is_regulated_supplier,
            agg.trailing_12m_spend, agg.invoice_count,
            agg.on_time_payment_pct, agg.avg_dpo,
            agg.measured_maverick_pct
        FROM {s.gold}.dim_supplier s
        LEFT JOIN ({_supplier_t12m_agg_sql(s)}) agg
            ON s.supplier_id = agg.supplier_id
        WHERE s.supplier_id = ?
        """,
        [supplier_id],
    )
    if not header:
        from fastapi import HTTPException
        raise HTTPException(404, f"Supplier {supplier_id} not found")

    # Category breakdown — T12M paid only, so it matches header spend.
    category_breakdown = fetch_all(
        caller,
        f"""
        SELECT true_category_primary AS category, ROUND(SUM(amount), 2) AS spend_usd
        FROM {s.gold}.fact_invoices
        WHERE supplier_id = ?
          AND invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
          AND payment_status = 'PAID'
        GROUP BY true_category_primary
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
            SELECT fiscal_year, fiscal_quarter, SUM(amount) AS spend_usd
            FROM {s.gold}.fact_invoices
            WHERE supplier_id = ?
              AND payment_status = 'PAID'
            GROUP BY fiscal_year, fiscal_quarter
            ORDER BY fiscal_year DESC, fiscal_quarter DESC
            LIMIT 8
        )
        SELECT fiscal_year, fiscal_quarter, ROUND(spend_usd, 2) AS spend_usd
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
