"""Spend Analytics dashboard endpoints.

Every metric here is sourced from the governed metric views (gold.mv_spend,
gold.mv_supplier_performance) via MEASURE() — the same single source of truth
the home KPIs, supplier scorecard, and Genie use. Ratio measures are stored as
fractions (0–1) in the views; we ×100 here to keep this API's percent-number
contract (the frontend's fmtPct just appends '%'). Spend measures are dollars.

All views filter to the trailing 12 months except spend_trend, which returns the
full fiscal history so the trend line can show the multi-year arc.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import CallerIdentity, caller_identity
from ..config import get_settings
from ..db import fetch_all, fetch_one

router = APIRouter(prefix="/analytics", tags=["analytics"])

# Dashboard dimension → mv_spend dimension name.
_COMPOSITION_DIMS = {
    "category": "category_primary",
    "segment": "segment",
    "pr_source": "pr_source",
}

_T12M = "invoice_date >= DATE_SUB(CURRENT_DATE(), 365)"


@router.get("/spend_composition", response_model=list[dict])
def spend_composition(
    dim: str = Query(default="category", description="category | segment | pr_source"),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    """T12M spend broken down by a dimension, split managed vs total (the
    frontend renders managed as a filled segment of the total bar)."""
    if dim not in _COMPOSITION_DIMS:
        raise HTTPException(400, f"dim must be one of {sorted(_COMPOSITION_DIMS)}")
    col = _COMPOSITION_DIMS[dim]
    s = get_settings()
    return fetch_all(
        caller,
        f"""
        SELECT
            {col}                          AS label,
            ROUND(MEASURE(total_spend), 2)   AS total_spend,
            ROUND(MEASURE(managed_spend), 2) AS managed_spend
        FROM {s.gold}.mv_spend
        WHERE {_T12M}
        GROUP BY ALL
        ORDER BY total_spend DESC
        """,
    )


@router.get("/managed_status", response_model=dict)
def managed_status(caller: CallerIdentity = Depends(caller_identity)) -> dict:
    """The four managed-status quadrants (Contracted & Sourced / Contracted only /
    Sourced only / Unmanaged) by spend + line count, plus the headline managed
    share by dollars vs by count (the 'small count of large buys' story)."""
    s = get_settings()
    quadrants = fetch_all(
        caller,
        f"""
        SELECT
            managed_status                   AS managed_status,
            ROUND(MEASURE(total_spend), 2)   AS spend,
            MEASURE(invoice_count)           AS lines
        FROM {s.gold}.mv_spend
        WHERE {_T12M}
        GROUP BY ALL
        ORDER BY spend DESC
        """,
    )
    head = fetch_one(
        caller,
        f"""
        SELECT
            ROUND(MEASURE(managed_spend_pct) * 100, 1)       AS managed_pct,
            ROUND(MEASURE(managed_spend_pct_count) * 100, 1) AS managed_pct_count
        FROM {s.gold}.mv_spend
        WHERE {_T12M}
        GROUP BY ALL
        """,
    ) or {}
    return {
        "quadrants": quadrants,
        "managed_pct": float(head.get("managed_pct") or 0),
        "managed_pct_count": float(head.get("managed_pct_count") or 0),
    }


@router.get("/spend_trend", response_model=list[dict])
def spend_trend(caller: CallerIdentity = Depends(caller_identity)) -> list[dict]:
    """Paid spend by fiscal quarter (full history), total + managed overlay."""
    s = get_settings()
    return fetch_all(
        caller,
        f"""
        SELECT
            fiscal_year, fiscal_quarter,
            ROUND(MEASURE(total_spend), 2)   AS total_spend,
            ROUND(MEASURE(managed_spend), 2) AS managed_spend
        FROM {s.gold}.mv_spend
        GROUP BY ALL
        ORDER BY fiscal_year ASC, fiscal_quarter ASC
        """,
    )


@router.get("/supplier_concentration", response_model=list[dict])
def supplier_concentration(
    limit: int = Query(default=20, le=100),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    """Top-N suppliers by T12M spend with a running cumulative share of the whole
    book (the cumulative_pct exposes tail concentration), plus managed / maverick /
    DPO from mv_supplier_performance."""
    s = get_settings()
    return fetch_all(
        caller,
        f"""
        SELECT
            supplier_id, supplier_name, trailing_spend,
            managed_spend_pct, measured_maverick_pct, avg_dpo,
            ROUND(100.0 * cum_spend / NULLIF(total_book, 0), 1) AS cumulative_pct
        FROM (
            SELECT
                supplier_id, supplier_name, trailing_spend,
                managed_spend_pct, measured_maverick_pct, avg_dpo,
                SUM(trailing_spend) OVER (
                    ORDER BY trailing_spend DESC
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                )                                  AS cum_spend,
                SUM(trailing_spend) OVER ()        AS total_book
            FROM (
                SELECT
                    supplier_id                                   AS supplier_id,
                    supplier_name                                 AS supplier_name,
                    ROUND(MEASURE(trailing_spend), 2)             AS trailing_spend,
                    ROUND(MEASURE(managed_spend_pct) * 100, 1)    AS managed_spend_pct,
                    ROUND(MEASURE(measured_maverick_pct) * 100, 1) AS measured_maverick_pct,
                    ROUND(MEASURE(avg_dpo), 1)                    AS avg_dpo
                FROM {s.gold}.mv_supplier_performance
                WHERE {_T12M}
                GROUP BY ALL
            )
        )
        ORDER BY trailing_spend DESC
        LIMIT ?
        """,
        [limit],
    )
