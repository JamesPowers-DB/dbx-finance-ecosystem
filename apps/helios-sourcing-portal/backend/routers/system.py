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
    """Home page KPI strip — trailing 12-month aggregates."""
    s = get_settings()
    row = fetch_one(
        caller,
        f"""
        SELECT
            ROUND(SUM(amount), 2)                                           AS total_spend_usd,
            ROUND(100.0 * SUM(CASE WHEN addressability = 'Addressable' THEN amount ELSE 0 END)
                  / NULLIF(SUM(amount), 0), 1)                              AS addressable_spend_pct,
            ROUND(SUM(CASE WHEN addressability = 'Addressable' THEN amount ELSE 0 END), 2)
                                                                            AS addressable_spend_usd,
            ROUND(100.0 * SUM(CASE WHEN predicted_secondary_category IS NOT NULL THEN amount ELSE 0 END)
                  / NULLIF(SUM(CASE WHEN addressability = 'Addressable' THEN amount ELSE 0 END), 0), 1)
                                                                            AS managed_spend_pct,
            ROUND(100.0 * SUM(CASE WHEN is_on_time_payment THEN 1 ELSE 0 END)
                  / NULLIF(COUNT(*), 0), 1)                                 AS on_time_payment_pct
        FROM {s.gold}.fact_invoices
        WHERE invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
        """,
    )

    # Contract coverage = active contract committed spend / trailing 12m addressable spend
    contract_row = fetch_one(
        caller,
        f"""
        SELECT ROUND(100.0 * COALESCE(c.total_committed_spend, 0)
               / NULLIF(agg.addressable_spend, 0), 1) AS contract_coverage_pct
        FROM (
            SELECT SUM(CASE WHEN addressability = 'Addressable' THEN amount ELSE 0 END)
                   AS addressable_spend
            FROM {s.gold}.fact_invoices
            WHERE invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
        ) agg
        CROSS JOIN (
            SELECT SUM(total_committed_spend) AS total_committed_spend
            FROM {s.silver}.contract_inbound
            WHERE contract_type IN ('Statement of Work', 'Framework')
              AND status = 'Active'
        ) c
        """,
    )

    r = row or {}
    cr = contract_row or {}
    return {
        "total_spend_usd": float(r.get("total_spend_usd") or 0),
        "managed_spend_pct": float(r.get("managed_spend_pct") or 0),
        "contract_coverage_pct": float(cr.get("contract_coverage_pct") or 0),
        "on_time_payment_pct": float(r.get("on_time_payment_pct") or 0),
        "addressable_spend_usd": float(r.get("addressable_spend_usd") or 0),
        "addressable_spend_pct": float(r.get("addressable_spend_pct") or 0),
    }
