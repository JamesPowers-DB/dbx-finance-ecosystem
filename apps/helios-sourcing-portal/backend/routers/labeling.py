"""Spend Labeling Monitor endpoints — ML coverage, confidence, disagreements."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..auth import CallerIdentity, caller_identity
from ..config import get_settings
from ..db import fetch_all

router = APIRouter(prefix="/labeling", tags=["labeling"])


@router.get("/coverage", response_model=list[dict])
def coverage(
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    """% of invoice lines with a non-null predicted_secondary_category, by quarter + segment."""
    s = get_settings()
    sql = f"""
        SELECT
            fiscal_year,
            fiscal_quarter,
            segment_code,
            COUNT(*)                                                    AS total_lines,
            SUM(CASE WHEN predicted_secondary_category IS NOT NULL
                     THEN 1 ELSE 0 END)                                 AS classified_lines,
            ROUND(
                100.0 * SUM(CASE WHEN predicted_secondary_category IS NOT NULL
                                 THEN 1 ELSE 0 END) / COUNT(*), 1
            )                                                           AS coverage_pct
        FROM {s.gold}.fact_invoices
        GROUP BY fiscal_year, fiscal_quarter, segment_code
        ORDER BY fiscal_year, fiscal_quarter, segment_code
    """
    return fetch_all(caller, sql)


@router.get("/confidence", response_model=list[dict])
def confidence_distribution(
    tier: str = Query(default="secondary", description="primary or secondary"),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    """Histogram of confidence scores (10 equal-width buckets 0–1)."""
    if tier not in {"primary", "secondary"}:
        from fastapi import HTTPException
        raise HTTPException(400, "tier must be primary or secondary")
    col = "secondary_confidence" if tier == "secondary" else "primary_confidence"
    s = get_settings()
    sql = f"""
        SELECT
            CONCAT(
                CAST(FLOOR({col} * 10) / 10 AS STRING),
                '–',
                CAST(FLOOR({col} * 10) / 10 + 0.1 AS STRING)
            )                                               AS bucket,
            COUNT(*)                                        AS count,
            '{tier}'                                        AS tier
        FROM {s.gold}.fact_invoices
        WHERE {col} IS NOT NULL
        GROUP BY FLOOR({col} * 10)
        ORDER BY FLOOR({col} * 10)
    """
    return fetch_all(caller, sql)


@router.get("/disagreements", response_model=list[dict])
def disagreements(
    limit: int = Query(default=200, le=1000),
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    """Invoice lines where true_category_secondary ≠ predicted_secondary_category."""
    s = get_settings()
    sql = f"""
        SELECT
            invoice_line_id,
            invoice_date,
            segment_code,
            supplier_name,
            line_description,
            amount,
            true_category_secondary,
            predicted_secondary_category,
            secondary_confidence
        FROM {s.gold}.fact_invoices
        WHERE predicted_secondary_category IS NOT NULL
          AND true_category_secondary IS NOT NULL
          AND true_category_secondary != predicted_secondary_category
        ORDER BY secondary_confidence ASC NULLS LAST
        LIMIT ?
    """
    return fetch_all(caller, sql, [limit])


@router.get("/model_history", response_model=list[dict])
def model_history(
    caller: CallerIdentity = Depends(caller_identity),
) -> list[dict]:
    """Model evaluation run history from ml.spend_clf_eval_runs."""
    s = get_settings()
    sql = f"""
        SELECT
            run_id,
            model_alias,
            eval_date,
            holdout_leaf_accuracy,
            maverick_leaf_accuracy,
            holdout_parent_accuracy
        FROM {s.ml}.spend_clf_eval_runs
        ORDER BY eval_date DESC
        LIMIT 50
    """
    return fetch_all(caller, sql)
