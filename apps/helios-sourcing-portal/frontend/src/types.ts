// Mirrored 1:1 from backend/models.py Pydantic models

export interface HealthResponse { status: string; }

export interface MeResponse {
  email: string;
  display_name: string;
  initials: string;
}

export interface KpiResponse {
  total_spend_usd: number;
  managed_spend_pct: number;
  classified_spend_pct: number;
  contract_coverage_pct: number;
  on_time_payment_pct: number;
  addressable_spend_usd: number;
  addressable_spend_pct: number;
}

export interface ContractRow {
  contract_workspace_id: string;
  contract_type: string;
  title: string;
  supplier_id: string;
  supplier_name: string | null;
  effective_date: string | null;
  expiration_date: string | null;
  total_committed_spend: number | null;
  actual_spend_to_date: number | null;
  pct_consumed: number | null;
  days_to_expiration: number | null;
  trailing_12m_spend: number | null;
  status: string;
  region: string | null;
}

export interface BurnDownPoint {
  period: string;
  cumulative_spend: number;
  committed_pct: number;
}

export interface ContractBurnDown {
  contract_workspace_id: string;
  title: string | null;
  total_committed_spend: number | null;
  points: BurnDownPoint[];
}

// Contract drilldown — Linked Invoices / Linked POs tabs.
export interface ContractInvoiceRow {
  invoice_line_id: string;
  invoice_date: string | null;
  amount: number | null;
  true_category_primary: string | null;
  payment_status: string | null;
}

export interface ContractPORow {
  po_number: string;
  po_line_num: number | null;
  extended_amount: number | null;
  true_category_primary: string | null;
}

export interface SupplierRow {
  supplier_id: string;
  supplier_name: string | null;
  region: string | null;
  category_primary: string | null;
  payment_terms: string | null;
  // % of T12M paid spend NOT matched to an active contract. Replaces the
  // synthetic maverick_propensity demo seed.
  measured_maverick_pct: number | null;
  is_regulated_supplier: boolean | null;
  trailing_12m_spend: number | null;
  invoice_count: number | null;
  on_time_payment_pct: number | null;
  avg_dpo: number | null;
}

export interface SupplierScorecard extends SupplierRow {
  country_code: string | null;
  category_breakdown: { category: string | null; spend_usd: number }[];
  contracts: {
    contract_workspace_id: string;
    contract_type: string;
    title: string;
    effective_date: string | null;
    expiration_date: string | null;
    total_committed_spend: number | null;
    status: string;
    pct_consumed: number | null;
    days_to_expiration: number | null;
  }[];
  spend_trend: {
    fiscal_year: number;
    fiscal_quarter: number;
    spend_usd: number;
  }[];
}

export interface RenegotiationTarget {
  supplier_id: string;
  supplier_name: string | null;
  current_payment_terms: string | null;
  current_dpo: number | null;
  target_dpo: number;
  working_capital_opportunity_usd: number;
  trailing_12m_spend: number | null;
  category_primary: string | null;
}

export interface CostReductionRow {
  savings_event_id: string;
  source_id: string;
  segment_code: string | null;
  fiscal_year: number;
  fiscal_quarter: number;
  category_primary: string | null;
  supplier_id: string | null;
  supplier_name: string | null;
  event_type: string;
  event_title: string | null;
  awarded_amount: number;
  baseline_amount: number;
  savings_amount_usd: number;
  savings_rate: number;
}

export interface AvoidanceEntry {
  entry_id: string;
  source_type: string;
  source_id: string | null;
  segment_code: string | null;
  fiscal_year: number;
  fiscal_quarter: number;
  category_primary: string | null;
  supplier_id: string | null;
  supplier_name: string | null;
  savings_amount_usd: number;
  baseline_context: string | null;
  notes: string | null;
  attested_by: string;
  attested_at: string;
  approved: boolean;
  approved_by: string | null;
  approved_at: string | null;
  rejected_at: string | null;
  rejection_reason: string | null;
}

export interface SavingsSummaryRow {
  segment_code: string | null;
  fiscal_year: number;
  fiscal_quarter: number;
  reduction_usd: number;
  // Approved avoidance only — pending entries are separate.
  avoidance_usd: number;
  pending_avoidance_usd: number;
  total_savings_usd: number;
  fpa_budget_usd: number | null;
  savings_pct_of_budget: number | null;
}

export interface AvoidanceEntryCreate {
  source_type?: string;
  source_id?: string | null;
  segment_code?: string | null;
  fiscal_year: number;
  fiscal_quarter: number;
  category_primary?: string | null;
  supplier_id?: string | null;
  supplier_name?: string | null;
  savings_amount_usd: number;
  baseline_context?: string | null;
  notes?: string | null;
}

export interface ChatSessionCreate {
  title?: string | null;
}

export interface ChatSession {
  session_id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
}

export interface ChatMessage {
  message_id: string;
  session_id: string;
  role: string;
  content: string;
  tool_calls: unknown | null;
  created_at: string;
}

export interface LabelingCoverageRow {
  fiscal_year: number;
  fiscal_quarter: number;
  segment_code: string;
  total_lines: number;
  classified_lines: number;
  coverage_pct: number;
}

export interface ConfidenceBucket {
  bucket: string;
  count: number;
  tier: string;
}

export interface DisagreementRow {
  invoice_line_id: string;
  invoice_date: string | null;
  segment_code: string | null;
  supplier_name: string | null;
  line_description: string | null;
  amount: number | null;
  true_category_secondary: string | null;
  predicted_secondary_category: string | null;
  secondary_confidence: number | null;
}

export interface ModelHistoryRow {
  run_id: string | null;
  model_alias: string | null;
  eval_date: string | null;
  holdout_leaf_accuracy: number | null;
  maverick_leaf_accuracy: number | null;
  holdout_parent_accuracy: number | null;
}
