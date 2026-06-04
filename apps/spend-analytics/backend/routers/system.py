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
        FROM {s.gold}.gold_mv_spend
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


@router.get("/attention")
def attention(caller: CallerIdentity = Depends(caller_identity)) -> dict:
    """Home "needs your attention" queue — the two UC-backed action items
    (the Cost-Savings attestation count is added client-side from
    /cost_savings/kpis, which owns the Lakebase ledger).

    - contracts: active SoW/Framework that are expiring within 120 days AND
      under-utilized (<50% consumed), OR already nearly exhausted (>=90%) — the
      same renewal-risk predicate the Contracts page and the chatbot's
      expiring_contracts tool use.
    - suppliers: among the top 25 suppliers by trailing-12m paid spend, those
      running below 50% managed — concentration with leakage. Ranking by spend
      (not an absolute $ threshold) keeps this self-calibrating across datasets.
    """
    s = get_settings()
    contracts = fetch_one(
        caller,
        f"""
        SELECT COUNT(*)                             AS count,
               ROUND(SUM(total_committed_spend), 0) AS committed_usd
        FROM {s.silver}.silver_contract_inbound
        WHERE contract_type IN ('Statement of Work', 'Framework')
          AND status = 'Active'
          AND effective_date <= CURRENT_DATE()
          AND expiration_date >= CURRENT_DATE()
          AND (
            (expiration_date <= DATE_ADD(CURRENT_DATE(), 120)
              AND COALESCE(100.0 * actual_spend_to_date / NULLIF(total_committed_spend, 0), 0) < 50)
            OR COALESCE(100.0 * actual_spend_to_date / NULLIF(total_committed_spend, 0), 0) >= 90
          )
        """,
    ) or {}

    suppliers = fetch_one(
        caller,
        f"""
        WITH sp AS (
            SELECT supplier_id,
                   MEASURE(trailing_spend)     AS spend,
                   MEASURE(managed_spend_pct)  AS managed
            FROM {s.gold}.gold_mv_supplier_performance
            WHERE invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
            GROUP BY supplier_id
        ),
        ranked AS (
            SELECT spend, managed, ROW_NUMBER() OVER (ORDER BY spend DESC) AS rk
            FROM sp
        )
        SELECT COUNT(*)             AS count,
               ROUND(SUM(spend), 0) AS spend_usd
        FROM ranked
        WHERE rk <= 25 AND managed < 0.5
        """,
    ) or {}

    return {
        "contracts": {
            "count": int(contracts.get("count") or 0),
            "committed_usd": float(contracts.get("committed_usd") or 0),
        },
        "suppliers": {
            "count": int(suppliers.get("count") or 0),
            "spend_usd": float(suppliers.get("spend_usd") or 0),
        },
    }
