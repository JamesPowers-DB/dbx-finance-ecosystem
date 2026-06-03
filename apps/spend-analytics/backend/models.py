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
    # Managed Spend = % of addressable paid spend matched to an active contract
    # or PR (the operational "under sourcing control" definition).
    managed_spend_pct: float
    # Classified Spend = % of addressable paid spend with an ML-predicted
    # secondary category (the ML-coverage definition that used to be called
    # "Managed Spend" pre-tightening).
    classified_spend_pct: float
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
    source_system: str | None = None


class BurnDownPoint(BaseModel):
    period: str          # "FY24 Q3"
    cumulative_spend: float
    committed_pct: float


class ContractBurnDown(BaseModel):
    contract_workspace_id: str
    title: str
    total_committed_spend: float | None
    points: list[BurnDownPoint]


# Drilldown rows for the contract side-panel tabs. Both queries reuse the
# same contract-scope filter: supplier_id matches + invoice/PO date inside
# the contract's effective–expiration window.

class ContractInvoiceRow(BaseModel):
    invoice_line_id: str
    invoice_date: date | None
    amount: float | None
    true_category_primary: str | None
    payment_status: str | None


class ContractPORow(BaseModel):
    po_number: str
    po_line_num: int | None
    extended_amount: float | None
    true_category_primary: str | None


# ── Suppliers ─────────────────────────────────────────────────────────────────

class SupplierRow(BaseModel):
    supplier_id: str
    supplier_name: str | None
    region: str | None
    category_primary: str | None
    payment_terms: str | None
    # Measured maverick spend %: % of T12M paid spend NOT matched to an active
    # contract for this supplier. Replaces the synthetic `maverick_propensity`
    # demo seed.
    measured_maverick_pct: float | None
    is_regulated_supplier: bool | None
    trailing_12m_spend: float | None
    invoice_count: int | None
    on_time_payment_pct: float | None
    avg_dpo: float | None


# ── Cost Savings (unified register) ───────────────────────────────────────────

class SavingsSubmit(BaseModel):
    """Payload to log a new savings record (lands as status='pending')."""
    artifact_type: str            # 'sourcing_event' | 'contract'
    artifact_id: str
    artifact_title: str | None = None
    savings_class: str            # 'reduction' | 'avoidance'
    savings_type: str             # taxonomy key (cost_savings.SAVINGS_TYPES)
    supplier_id: str | None = None
    supplier_name: str | None = None
    segment_code: str | None = None
    fiscal_year: int
    fiscal_quarter: int
    baseline_amount_usd: float | None = None
    realized_amount_usd: float | None = None
    savings_amount_usd: float
    baseline_context: str | None = None
    notes: str | None = None


class SavingsRejectBody(BaseModel):
    reason: str


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


