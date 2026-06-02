"""Spend Analytics dashboard endpoints.

Every metric here is sourced from the governed metric views (gold.mv_spend,
gold.mv_supplier_performance, gold.mv_purchase_orders) via MEASURE() — the same
single source of truth the home KPIs, supplier scorecard, and Genie use. Ratio
measures are stored as fractions (0–1) in the views; we ×100 here to keep this
API's percent-number contract (the frontend's fmtPct just appends '%'). Spend
measures are dollars.

A single `range` query param (90d | t12m | t24m | all) is the page's global time
window — every widget honors it so the whole page moves together. `_window()`
turns it into a WHERE fragment against whichever date column a view exposes.
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

# Global page time-range → lookback in days (None = no filter / all time).
_RANGES = {"90d": 90, "t12m": 365, "t24m": 730, "all": None}

# Trend grain → DATE_TRUNC unit. The window comes from the global range, not the
# grain, so the range control and the grain control compose cleanly.
_GRAIN_UNIT = {"daily": "DAY", "weekly": "WEEK", "monthly": "MONTH", "quarterly": "QUARTER"}


def _window(range_key: str, col: str) -> str:
    """SQL boolean for the selected window against date column `col`."""
    if range_key not in _RANGES:
        raise HTTPException(400, f"range must be one of {sorted(_RANGES)}")
    days = _RANGES[range_key]
    return f"{col} >= DATE_SUB(CURRENT_DATE(), {days})" if days else "1=1"


@router.get("/kpis", response_model=dict)
def kpis(
    range: str = Query(default="t12m", description="90d | t12m | t24m | all"),
    caller: CallerIdentity = Depends(caller_identity),
) -> dict:
    """Headline KPIs for the page strip — all from mv_spend MEASURE()s, so they
    tie exactly to the home page, the supplier scorecard, and Genie."""
    s = get_settings()
    return fetch_one(
        caller,
        f"""
        SELECT
            ROUND(MEASURE(total_spend), 2)               AS total_spend,
            ROUND(MEASURE(addressable_spend), 2)         AS addressable_spend,
            ROUND(MEASURE(managed_spend_pct) * 100, 1)   AS managed_pct,
            ROUND(MEASURE(on_time_payment_pct) * 100, 1) AS on_time_pct,
            ROUND(MEASURE(avg_dpo), 1)                   AS avg_dpo,
            COUNT(DISTINCT supplier_id)                  AS active_suppliers
        FROM {s.gold}.mv_spend
        WHERE {_window(range, "invoice_date")}
        GROUP BY ALL
        """,
    ) or {}


@router.get("/spend_composition", response_model=list[dict])
def spend_composition(
    dim: str = Query(default="category", description="category | segment | pr_source"),
    range: str = Query(default="t12m", description="90d | t12m | t24m | all"),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    """Spend broken down by a dimension, split managed vs total (the frontend
    renders managed as a filled segment of the total bar)."""
    if dim not in _COMPOSITION_DIMS:
        raise HTTPException(400, f"dim must be one of {sorted(_COMPOSITION_DIMS)}")
    col = _COMPOSITION_DIMS[dim]
    s = get_settings()
    return fetch_all(
        caller,
        f"""
        SELECT
            {col}                            AS label,
            ROUND(MEASURE(total_spend), 2)   AS total_spend,
            ROUND(MEASURE(managed_spend), 2) AS managed_spend
        FROM {s.gold}.mv_spend
        WHERE {_window(range, "invoice_date")}
        GROUP BY ALL
        ORDER BY total_spend DESC
        """,
    )


@router.get("/composition_detail", response_model=list[dict])
def composition_detail(
    dim: str = Query(description="category | segment | pr_source"),
    value: str = Query(description="the slice label clicked in the composition chart"),
    range: str = Query(default="t12m", description="90d | t12m | t24m | all"),
    limit: int = Query(default=8, le=50),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    """Top suppliers within one composition slice — powers the inline drill that
    opens when a composition bar is clicked. Same governed mv_spend measures,
    just filtered to the chosen dimension value."""
    if dim not in _COMPOSITION_DIMS:
        raise HTTPException(400, f"dim must be one of {sorted(_COMPOSITION_DIMS)}")
    col = _COMPOSITION_DIMS[dim]
    s = get_settings()
    return fetch_all(
        caller,
        f"""
        SELECT
            supplier_id, supplier_name,
            ROUND(MEASURE(total_spend), 2)             AS total_spend,
            ROUND(MEASURE(managed_spend), 2)           AS managed_spend,
            ROUND(MEASURE(managed_spend_pct) * 100, 1) AS managed_pct
        FROM {s.gold}.mv_spend
        WHERE {col} = ? AND {_window(range, "invoice_date")}
        GROUP BY ALL
        ORDER BY total_spend DESC
        LIMIT ?
        """,
        [value, limit],
    )


@router.get("/managed_status", response_model=dict)
def managed_status(
    range: str = Query(default="t12m", description="90d | t12m | t24m | all"),
    caller: CallerIdentity = Depends(caller_identity),
) -> dict:
    """The four managed-status quadrants (Contracted & Sourced / Contracted only /
    Sourced only / Unmanaged) by spend + line count, plus the headline managed
    share by dollars vs by count (the 'small count of large buys' story)."""
    s = get_settings()
    win = _window(range, "invoice_date")
    quadrants = fetch_all(
        caller,
        f"""
        SELECT
            managed_status                   AS managed_status,
            ROUND(MEASURE(total_spend), 2)   AS spend,
            MEASURE(invoice_count)           AS lines
        FROM {s.gold}.mv_spend
        WHERE {win}
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
        WHERE {win}
        GROUP BY ALL
        """,
    ) or {}
    return {
        "quadrants": quadrants,
        "managed_pct": float(head.get("managed_pct") or 0),
        "managed_pct_count": float(head.get("managed_pct_count") or 0),
    }


@router.get("/spend_trend", response_model=list[dict])
def spend_trend(
    grain: str = Query(default="monthly", description="daily | weekly | monthly | quarterly"),
    range: str = Query(default="t12m", description="90d | t12m | t24m | all"),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    """Paid spend over time, total + managed overlay. `grain` sets the bucket
    size (DATE_TRUNC unit); the global `range` sets the window. `period` is a
    truncated `invoice_date` (ISO) so the frontend renders a temporal axis."""
    if grain not in _GRAIN_UNIT:
        raise HTTPException(400, f"grain must be one of {sorted(_GRAIN_UNIT)}")
    unit = _GRAIN_UNIT[grain]
    s = get_settings()
    return fetch_all(
        caller,
        f"""
        SELECT
            DATE_TRUNC('{unit}', invoice_date) AS period,
            ROUND(MEASURE(total_spend), 2)     AS total_spend,
            ROUND(MEASURE(managed_spend), 2)   AS managed_spend
        FROM {s.gold}.mv_spend
        WHERE {_window(range, "invoice_date")}
        GROUP BY ALL
        ORDER BY period ASC
        """,
    )


@router.get("/lifecycle_funnel", response_model=list[dict])
def lifecycle_funnel(
    range: str = Query(default="t12m", description="90d | t12m | t24m | all"),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    """The source→pay value funnel: requisition estimate → committed PO value →
    realized (paid) spend, all from governed metric views. Each downstream stage
    carries the leakage that escaped management at that step, so the page can
    point at *where* to act (off-contract POs, then the unmanaged paid tail).

    PR/PO stages come from mv_purchase_orders (windowed on po_created_date);
    the paid stage from mv_spend (windowed on invoice_date). This is a value-flow
    funnel, not a strict subset — estimate vs actual means stages aren't
    guaranteed monotonic."""
    s = get_settings()
    po = fetch_one(
        caller,
        f"""
        SELECT
            ROUND(MEASURE(total_pr_estimate), 2)      AS requested,
            ROUND(MEASURE(total_po_amount), 2)        AS committed,
            ROUND(MEASURE(off_contract_po_amount), 2) AS po_leakage
        FROM {s.gold}.mv_purchase_orders
        WHERE {_window(range, "po_created_date")}
        GROUP BY ALL
        """,
    ) or {}
    paid = fetch_one(
        caller,
        f"""
        SELECT
            ROUND(MEASURE(total_spend), 2)     AS paid,
            ROUND(MEASURE(unmanaged_spend), 2) AS unmanaged
        FROM {s.gold}.mv_spend
        WHERE {_window(range, "invoice_date")}
        GROUP BY ALL
        """,
    ) or {}
    return [
        {
            "stage": "Requested",
            "caption": "Requisition estimate (converted PRs)",
            "amount": float(po.get("requested") or 0),
            "leak": None,
            "leak_label": None,
        },
        {
            "stage": "Committed",
            "caption": "Purchase-order value",
            "amount": float(po.get("committed") or 0),
            "leak": float(po.get("po_leakage") or 0),
            "leak_label": "off-contract PO",
        },
        {
            "stage": "Paid",
            "caption": "Realized (paid) spend",
            "amount": float(paid.get("paid") or 0),
            "leak": float(paid.get("unmanaged") or 0),
            "leak_label": "unmanaged tail",
        },
    ]


@router.get("/supplier_concentration", response_model=list[dict])
def supplier_concentration(
    limit: int = Query(default=20, le=100),
    range: str = Query(default="t12m", description="90d | t12m | t24m | all"),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    """Top-N suppliers by spend in the window with a running cumulative share of
    the whole book (cumulative_pct exposes tail concentration), plus managed /
    maverick / DPO from mv_supplier_performance."""
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
                WHERE {_window(range, "invoice_date")}
                GROUP BY ALL
            )
        )
        ORDER BY trailing_spend DESC
        LIMIT ?
        """,
        [limit],
    )
