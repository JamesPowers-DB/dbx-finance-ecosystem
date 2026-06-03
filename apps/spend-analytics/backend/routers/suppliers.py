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
        FROM {s.gold}.gold_mv_supplier_performance
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
        FROM {s.gold}.gold_mv_spend
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
        FROM {s.silver}.silver_contract_inbound
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
    # trend line chart renders left-to-right chronologically.
    spend_trend = fetch_all(
        caller,
        f"""
        WITH q AS (
            SELECT fiscal_year, fiscal_quarter, ROUND(MEASURE(total_spend), 2) AS spend_usd
            FROM {s.gold}.gold_mv_spend
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

    # Dimensional attributes from the supplier master. `aliases_resolved` counts
    # the source records that entity-resolution collapsed into this supplier —
    # a nice "one governed supplier from N feeds" detail for the demo.
    attributes = fetch_all(
        caller,
        f"""
        SELECT
            d.country_code, d.region, d.created_date, d.category_primary,
            d.segment_affinity, d.payment_terms, d.is_regulated_supplier,
            d.entity_resolution_cluster_id,
            (SELECT COUNT(*) FROM {s.gold}.gold_dim_supplier x
             WHERE x.entity_resolution_cluster_id = d.entity_resolution_cluster_id) AS aliases_resolved
        FROM {s.gold}.gold_dim_supplier d
        WHERE d.supplier_id = ?
        """,
        [supplier_id],
    )

    # Spend economics — the bases the renegotiation what-if model needs, all T12M
    # paid, all from mv_spend so they reconcile with the header.
    economics = fetch_all(
        caller,
        f"""
        SELECT
            ROUND(MEASURE(total_spend), 2)       AS paid_spend,
            ROUND(MEASURE(addressable_spend), 2) AS addressable_spend,
            ROUND(MEASURE(managed_spend), 2)     AS managed_spend,
            ROUND(MEASURE(unmanaged_spend), 2)   AS unmanaged_spend
        FROM {s.gold}.gold_mv_spend
        WHERE supplier_id = ?
          AND invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
        GROUP BY ALL
        """,
        [supplier_id],
    )

    # ML spend-classification results for this supplier (T12M paid): the predicted
    # category mix + per-category confidence, plus headline agreement (predicted ==
    # true) and coverage. Sourced from fact_invoices (carries the model output).
    classification_mix = fetch_all(
        caller,
        f"""
        SELECT
            predicted_primary_category        AS category,
            ROUND(SUM(amount), 2)             AS spend_usd,
            COUNT(*)                          AS lines,
            ROUND(AVG(primary_confidence), 3) AS avg_confidence
        FROM {s.gold}.gold_fact_invoices
        WHERE supplier_id = ?
          AND payment_status = 'PAID'
          AND invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
          AND predicted_primary_category IS NOT NULL
        GROUP BY ALL
        ORDER BY spend_usd DESC
        LIMIT 6
        """,
        [supplier_id],
    )
    classification_summary = fetch_all(
        caller,
        f"""
        SELECT
            ROUND(AVG(primary_confidence), 3) AS avg_confidence,
            ROUND(100.0 * COUNT(predicted_primary_category) / NULLIF(COUNT(*), 0), 1) AS classified_pct,
            ROUND(100.0 * SUM(CASE WHEN predicted_primary_category = true_category_primary THEN 1 ELSE 0 END)
                  / NULLIF(COUNT(predicted_primary_category), 0), 1) AS agreement_pct
        FROM {s.gold}.gold_fact_invoices
        WHERE supplier_id = ?
          AND payment_status = 'PAID'
          AND invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
        """,
        [supplier_id],
    )

    # Top 5 spend commitments — POs by committed value (extended_amount), with
    # status, date, category, and whether the commitment is on contract/sourced.
    top_commitments = fetch_all(
        caller,
        f"""
        SELECT
            po_number,
            MIN(po_created_date)           AS po_date,
            MAX(po_status)                 AS po_status,
            ROUND(SUM(extended_amount), 2) AS committed_usd,
            MAX(true_category_primary)     AS category,
            MAX(CASE WHEN contract_id IS NOT NULL OR sourcing_event_id IS NOT NULL
                     THEN 1 ELSE 0 END)    AS on_contract
        FROM {s.gold}.gold_fact_purchase_orders
        WHERE supplier_id = ?
          AND po_created_date >= DATE_SUB(CURRENT_DATE(), 365)
        GROUP BY po_number
        ORDER BY committed_usd DESC
        LIMIT 5
        """,
        [supplier_id],
    )

    return {
        **header[0],
        "attributes": attributes[0] if attributes else {},
        "economics": economics[0] if economics else {},
        "classification_summary": classification_summary[0] if classification_summary else {},
        "classification_mix": classification_mix,
        "top_commitments": top_commitments,
        "category_breakdown": category_breakdown,
        "contracts": contracts,
        "spend_trend": spend_trend,
    }
