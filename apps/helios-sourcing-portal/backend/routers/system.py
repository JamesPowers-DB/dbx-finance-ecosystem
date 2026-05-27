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
            -- Classified Spend (ML coverage): % of addressable paid spend
            -- with an ML-predicted secondary category. This is the metric
            -- the home page used to mislabel as "Managed Spend".
            ROUND(100.0 * SUM(CASE
                    WHEN addressability = 'Addressable'
                     AND predicted_secondary_category IS NOT NULL
                    THEN amount ELSE 0 END)
                  / NULLIF(SUM(CASE WHEN addressability = 'Addressable' THEN amount ELSE 0 END), 0), 1)
                                                                            AS classified_spend_pct,
            -- Spend-weighted on-time payment %: $-weighted, not line-count.
            ROUND(100.0 * SUM(CASE WHEN is_on_time_payment THEN amount ELSE 0 END)
                  / NULLIF(SUM(amount), 0), 1)                              AS on_time_payment_pct
        FROM {s.gold}.fact_invoices
        WHERE invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
          AND payment_status = 'PAID'
        """,
    )

    # Managed Spend (operational): % of T12M addressable paid spend that is
    # linked to procurement governance — either flagged as PO-matched
    # (`po_matched_flag = 'Y'`, the 3-way match signal) OR covered by an
    # active SOW/Framework contract for the same supplier within the
    # contract's effective–expiration window.
    #
    # IMPORTANT: use EXISTS for the contract check, not JOIN. A LEFT JOIN
    # fans out when a supplier has multiple overlapping active contracts,
    # double-counting the invoice amount and pushing the percentage above
    # 100%. EXISTS gives a true row-level boolean.
    #
    # (The old "Managed Spend" metric was actually ML coverage; we surface
    # that separately as classified_spend_pct.)
    managed_row = fetch_one(
        caller,
        f"""
        WITH addressable AS (
            SELECT supplier_id, invoice_date, amount, po_matched_flag
            FROM {s.gold}.fact_invoices
            WHERE invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
              AND payment_status = 'PAID'
              AND addressability = 'Addressable'
        )
        SELECT
            ROUND(100.0 * SUM(CASE
                WHEN po_matched_flag = 'Y' OR EXISTS (
                    SELECT 1 FROM {s.silver}.contract_inbound c
                    WHERE c.supplier_id = addressable.supplier_id
                      AND c.status = 'Active'
                      AND c.contract_type IN ('Statement of Work', 'Framework')
                      AND addressable.invoice_date BETWEEN c.effective_date AND c.expiration_date
                )
                THEN amount ELSE 0 END)
                / NULLIF(SUM(amount), 0), 1) AS managed_spend_pct
        FROM addressable
        """,
    )

    # Contract coverage: % of T12M paid addressable spend covered by an
    # active SOW/Framework contract for the same supplier in the same
    # period. Same EXISTS pattern as managed_spend to avoid fanout from
    # overlapping contracts. Replaces the prior formula that compared
    # multi-year commitments to T12M invoices (could exceed 100% and was
    # meaningless across mismatched horizons).
    contract_row = fetch_one(
        caller,
        f"""
        WITH addressable AS (
            SELECT supplier_id, invoice_date, amount
            FROM {s.gold}.fact_invoices
            WHERE invoice_date >= DATE_SUB(CURRENT_DATE(), 365)
              AND payment_status = 'PAID'
              AND addressability = 'Addressable'
        )
        SELECT
            ROUND(100.0 * SUM(CASE WHEN EXISTS (
                SELECT 1 FROM {s.silver}.contract_inbound c
                WHERE c.supplier_id = addressable.supplier_id
                  AND c.status = 'Active'
                  AND c.contract_type IN ('Statement of Work', 'Framework')
                  AND addressable.invoice_date BETWEEN c.effective_date AND c.expiration_date
            ) THEN amount ELSE 0 END)
                / NULLIF(SUM(amount), 0), 1) AS contract_coverage_pct
        FROM addressable
        """,
    )

    r = row or {}
    cr = contract_row or {}
    mr = managed_row or {}
    return {
        "total_spend_usd": float(r.get("total_spend_usd") or 0),
        "managed_spend_pct": float(mr.get("managed_spend_pct") or 0),
        "classified_spend_pct": float(r.get("classified_spend_pct") or 0),
        "contract_coverage_pct": float(cr.get("contract_coverage_pct") or 0),
        "on_time_payment_pct": float(r.get("on_time_payment_pct") or 0),
        "addressable_spend_usd": float(r.get("addressable_spend_usd") or 0),
        "addressable_spend_pct": float(r.get("addressable_spend_pct") or 0),
    }
