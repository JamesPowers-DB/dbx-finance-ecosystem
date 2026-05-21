"""Pydantic response models — mirrored 1:1 in frontend types.ts."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel


# ── System ────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str


class MeResponse(BaseModel):
    email: str
    display_name: str
    initials: str


# ── Home / KPIs ───────────────────────────────────────────────────────────────

class KpiResponse(BaseModel):
    total_spend_usd: float
    managed_spend_pct: float
    contract_coverage_pct: float
    on_time_payment_pct: float
    addressable_spend_usd: float
    addressable_spend_pct: float


# ── Contracts ─────────────────────────────────────────────────────────────────

class ContractRow(BaseModel):
    contract_workspace_id: str
    contract_type: str
    title: str
    supplier_id: str
    supplier_name: str | None
    effective_date: date | None
    expiration_date: date | None
    total_committed_spend: float | None
    actual_spend_to_date: float | None
    pct_consumed: float | None
    days_to_expiration: int | None
    trailing_12m_spend: float | None
    status: str
    region: str | None


class BurnDownPoint(BaseModel):
    period: str          # "FY24 Q3"
    cumulative_spend: float
    committed_pct: float


class ContractBurnDown(BaseModel):
    contract_workspace_id: str
    title: str
    total_committed_spend: float | None
    points: list[BurnDownPoint]


# ── Suppliers ─────────────────────────────────────────────────────────────────

class SupplierRow(BaseModel):
    supplier_id: str
    supplier_name: str | None
    region: str | None
    category_primary: str | None
    payment_terms: str | None
    maverick_propensity: float | None
    is_regulated_supplier: bool | None
    trailing_12m_spend: float | None
    invoice_count: int | None
    on_time_payment_pct: float | None
    avg_dpo: float | None


class RenegotiationTarget(BaseModel):
    supplier_id: str
    supplier_name: str | None
    current_payment_terms: str | None
    current_dpo: float | None
    target_dpo: int
    working_capital_opportunity_usd: float
    trailing_12m_spend: float | None
    category_primary: str | None


# ── Cost Savings ──────────────────────────────────────────────────────────────

class CostReductionRow(BaseModel):
    savings_event_id: str
    source_id: str
    segment_code: str | None
    fiscal_year: int
    fiscal_quarter: int
    category_primary: str | None
    supplier_id: str | None
    supplier_name: str | None
    event_type: str
    event_title: str | None
    awarded_amount: float
    baseline_amount: float
    savings_amount_usd: float
    savings_rate: float


class AvoidanceEntry(BaseModel):
    entry_id: str
    source_type: str
    source_id: str | None
    segment_code: str | None
    fiscal_year: int
    fiscal_quarter: int
    category_primary: str | None
    supplier_id: str | None
    supplier_name: str | None
    savings_amount_usd: float
    baseline_context: str | None
    notes: str | None
    attested_by: str
    attested_at: datetime
    approved: bool


class AvoidanceEntryCreate(BaseModel):
    source_type: str = "manual"
    source_id: str | None = None
    segment_code: str | None = None
    fiscal_year: int
    fiscal_quarter: int
    category_primary: str | None = None
    supplier_id: str | None = None
    supplier_name: str | None = None
    savings_amount_usd: float
    baseline_context: str | None = None
    notes: str | None = None


class SavingsSummaryRow(BaseModel):
    segment_code: str | None
    fiscal_year: int
    fiscal_quarter: int
    reduction_usd: float
    avoidance_usd: float
    total_savings_usd: float
    fpa_budget_usd: float | None
    savings_pct_of_budget: float | None


# ── Chatbot ───────────────────────────────────────────────────────────────────

class ChatSession(BaseModel):
    session_id: str
    title: str | None
    created_at: datetime
    updated_at: datetime


class ChatMessage(BaseModel):
    message_id: str
    session_id: str
    role: str
    content: str
    tool_calls: Any | None
    created_at: datetime


class ChatSessionCreate(BaseModel):
    title: str | None = None


class ChatMessageCreate(BaseModel):
    content: str


# ── Labeling Monitor ──────────────────────────────────────────────────────────

class LabelingCoverageRow(BaseModel):
    fiscal_year: int
    fiscal_quarter: int
    segment_code: str
    total_lines: int
    classified_lines: int
    coverage_pct: float


class ConfidenceBucket(BaseModel):
    bucket: str       # e.g. "0.0–0.1"
    count: int
    tier: str         # "primary" or "secondary"


class DisagreementRow(BaseModel):
    invoice_line_id: str
    invoice_date: date | None
    segment_code: str | None
    supplier_name: str | None
    line_description: str | None
    amount: float | None
    true_category_secondary: str | None
    predicted_secondary_category: str | None
    secondary_confidence: float | None


class ModelHistoryRow(BaseModel):
    run_id: str | None
    model_alias: str | None
    eval_date: datetime | None
    holdout_leaf_accuracy: float | None
    maverick_leaf_accuracy: float | None
    holdout_parent_accuracy: float | None
