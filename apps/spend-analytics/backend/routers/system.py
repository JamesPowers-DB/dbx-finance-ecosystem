"""System endpoints: healthz, me, and home KPIs."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..auth import CallerIdentity, caller_identity
from ..config import get_settings
from ..db import fetch_one
from ..models import HealthResponse, KpiResponse, MeResponse

router = APIRouter(tags=["system"])


@router.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/me", response_model=MeResponse)
def me(caller: CallerIdentity = Depends(caller_identity)) -> MeResponse:
    return MeResponse(
        email=caller.email,
        display_name=caller.display_name,
        initials=caller.initials,
    )


@router.get("/kpis", response_model=KpiResponse)
def kpis(caller: CallerIdentity = Depends(caller_identity)) -> dict:
    """Home page KPI strip — trailing 12-month aggregates.

    All spend metrics filter to `payment_status = 'PAID'` so unpaid /
    past-due invoices (commitments) are not counted as realized spend.
    On-time payment is spend-weighted so a $5M line carries 100,000x the
    weight of a $50 line.
    """
    # Single query against the governed spend metric view (gold.mv_spend) — one
    # source of truth shared with the app, Genie, and dashboards. Ratio measures
    # are stored as fractions (0–1); we ×100 here to preserve this endpoint's
    # historical percent-number contract (the frontend's fmtPct just appends '%').
    #
    # Managed Spend is now lineage-true (contracted OR competitively sourced),
    # NOT the old PO-matched-OR-contract heuristic — so this value is materially
    # lower (~50% vs the prior 99.6%) and finally defensible. PO-match is surfaced
    # separately by the metric view as po_coverage_pct (AP hygiene, not shown here).
    s = get_settings()
    row = fetch_one(
        caller,
        f"""
        SELECT
            ROUND(MEASURE(total_spend), 2)                  AS total_spend_usd,
            ROUND(MEASURE(addressable_spend), 2)            AS addressable_spend_usd,
            ROUND(MEASURE(managed_spend_pct) * 100, 1)      AS managed_spend_pct,
            ROUND(MEASURE(contract_coverage_pct) * 100, 1)  AS contract_coverage_pct,
            ROUND(MEASURE(classified_spend_pct) * 100, 1)   AS classified_spend_pct,
            ROUND(MEASURE(on_time_payment_pct) * 100, 1)    AS on_time_payment_pct
        FROM {s.gold}.mv_spend
        WHERE invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
        GROUP BY ALL
        """,
    )

    r = row or {}
    total = float(r.get("total_spend_usd") or 0)
    addressable = float(r.get("addressable_spend_usd") or 0)
    return {
        "total_spend_usd": total,
        "managed_spend_pct": float(r.get("managed_spend_pct") or 0),
        "classified_spend_pct": float(r.get("classified_spend_pct") or 0),
        "contract_coverage_pct": float(r.get("contract_coverage_pct") or 0),
        "on_time_payment_pct": float(r.get("on_time_payment_pct") or 0),
        "addressable_spend_usd": addressable,
        "addressable_spend_pct": round(100.0 * addressable / total, 1) if total else 0.0,
    }
