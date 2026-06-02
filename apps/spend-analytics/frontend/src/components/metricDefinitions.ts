// Central catalog of metric definitions surfaced via <MetricTooltip>.
//
// Single source of truth for what each KPI / column / pill MEANS so demo
// narration stays consistent across pages. Edit copy here — never in the
// page components — when refining wording before a demo.
//
// Convention: every entry includes period + definition + formula + filters
// so the popover lays out predictably. The wording mirrors the backend SQL
// in `routers/` (paid-invoice predicate, T12M window, contract-scoped joins).

import type { MetricTooltipContent } from "./MetricTooltip";

type Metric = MetricTooltipContent;

// ── Home KPIs ────────────────────────────────────────────────────────────────

const totalSpend: Metric = {
  metric: "Total Spend",
  period: "Trailing 12 months",
  definition: "Realized supplier spend over the last 365 days.",
  formula: "SUM(amount) on PAID invoice lines",
  filters: "payment_status = 'PAID' AND invoice_date >= today − 365d",
};

const managedSpend: Metric = {
  metric: "Managed Spend",
  period: "Trailing 12 months",
  definition:
    "Share of addressable paid spend under sourcing management — purchased under an active contract OR won through a competitive sourcing event, traced by document lineage on the invoice line. Excludes PO-match (that's AP hygiene, shown separately). Sourced via the governed gold.mv_spend metric view.",
  formula:
    "SUM(addressable spend where contract_id IS NOT NULL OR sourcing_event_id IS NOT NULL) / SUM(addressable spend)",
  filters:
    "payment_status = 'PAID' AND addressability = 'Addressable' AND invoice_date in T12M",
};

const classifiedSpend: Metric = {
  metric: "Classified Spend",
  period: "Trailing 12 months",
  definition:
    "Share of addressable paid spend with an ML-predicted secondary category. This is the ML-coverage view (previously mislabeled as 'Managed Spend').",
  formula:
    "SUM(addressable spend where predicted_secondary_category IS NOT NULL) / SUM(addressable spend)",
  filters: "payment_status = 'PAID' AND addressability = 'Addressable' AND invoice_date in T12M",
};

const contractCoverage: Metric = {
  metric: "Contract Coverage",
  period: "Trailing 12 months",
  definition:
    "Share of addressable paid spend on invoice lines linked to a contract (contract_id present via PR→PO→invoice lineage). Sourced via the governed gold.mv_spend metric view.",
  formula:
    "SUM(addressable spend where contract_id IS NOT NULL) / SUM(addressable paid spend), T12M",
  filters:
    "payment_status = 'PAID' AND addressability = 'Addressable' AND invoice_date in T12M",
};

const onTimePayment: Metric = {
  metric: "On-Time Payment %",
  period: "Trailing 12 months",
  definition:
    "Spend-weighted percentage of paid invoices where the payment date was on or before the due date. the enterprise paying suppliers on time — not supplier delivery OTD.",
  formula: "SUM(amount where is_on_time_payment) / SUM(amount)",
  filters: "payment_status = 'PAID' AND invoice_date in T12M",
};

// ── Suppliers (list + drilldown) ─────────────────────────────────────────────

const t12mSupplierSpend: Metric = {
  metric: "T12M Spend",
  period: "Trailing 12 months",
  definition: "Paid invoice spend with this supplier over the last 365 days.",
  formula: "SUM(amount) on PAID invoices for the supplier",
  filters: "payment_status = 'PAID' AND invoice_date >= today − 365d",
};

const invoiceCount: Metric = {
  metric: "Invoices",
  period: "Trailing 12 months",
  definition: "Count of paid invoice lines from this supplier in the T12M window.",
  formula: "COUNT(*) on PAID invoice lines",
  filters: "payment_status = 'PAID' AND invoice_date in T12M",
};

const avgDpo: Metric = {
  metric: "Avg DPO",
  period: "Trailing 12 months",
  definition:
    "Average days-to-pay across the supplier's paid invoices. Lower than current payment terms means the enterprise is paying early.",
  formula: "AVG(days_to_pay) on PAID invoices",
  filters: "payment_status = 'PAID' AND invoice_date in T12M",
};

const measuredMaverick: Metric = {
  metric: "Maverick Spend %",
  period: "Trailing 12 months",
  definition:
    "Share of the supplier's T12M paid spend NOT under management — neither on contract nor competitively sourced (off-contract leakage). Sourced via the governed gold.mv_supplier_performance metric view; matches the home Managed Spend definition.",
  formula:
    "SUM(amount where contract_id IS NULL AND sourcing_event_id IS NULL) / SUM(amount), supplier-scoped",
  filters: "payment_status = 'PAID' AND invoice_date in T12M",
};

const paymentTerms: Metric = {
  metric: "Payment Terms",
  period: "Current",
  definition:
    "Negotiated supplier payment terms (e.g. Net30 = invoice due 30 days after issue). Source: supplier master.",
  formula: "dim_supplier.payment_terms",
};

const workingCapitalOpp: Metric = {
  metric: "Working-Capital Opportunity",
  period: "Trailing 12 months annualized",
  definition:
    "Dollars of working capital freed up by extending this supplier from current DPO toward the target DPO bucket. Stretches Net15 → 45, Net30/45 → 60.",
  formula: "T12M spend / 365 × MAX(0, target_dpo − current_dpo)",
  filters: "regulated suppliers excluded; T12M spend > $100k; terms in {Net15, Net30, Net45}",
};

// ── Contracts ────────────────────────────────────────────────────────────────

const contractCommitted: Metric = {
  metric: "Committed Spend",
  period: "Full contract term",
  definition:
    "Total contractual commitment (the dollar ceiling negotiated with the supplier). Source: Ariba SOW/Framework master.",
  formula: "contract_inbound.total_committed_spend",
};

const pctConsumed: Metric = {
  metric: "% Consumed",
  period: "Effective date → today",
  definition:
    "Share of the contract commitment burned down by paid invoices to the supplier inside the contract's effective–expiration window.",
  formula:
    "SUM(paid invoice amount where invoice_date in [effective, expiration]) / total_committed_spend",
  filters: "payment_status = 'PAID' AND supplier matches contract",
};

const expires: Metric = {
  metric: "Expires",
  period: "Current",
  definition:
    "Days until contract expiration. Color-coded: red < 60d, amber < 120d, neutral otherwise.",
  formula: "DATEDIFF(expiration_date, today)",
};

const burnDown: Metric = {
  metric: "Burn-Down",
  period: "Contract effective date → expiration date",
  definition:
    "Cumulative paid invoice spend against this contract, by fiscal quarter. Scoped to invoices that landed inside the contract window — not supplier-wide.",
  formula:
    "Quarterly SUM(amount) with running cumulative; dashed reference at total_committed_spend",
  filters: "payment_status = 'PAID' AND supplier = contract.supplier_id",
};

const contractTypePill: Metric = {
  metric: "Contract Type",
  period: "Source-system value",
  definition:
    "Statement of Work — single project; Framework — multi-PR umbrella agreement. Other types (NDA, MSA) are excluded from list views to keep focus on spendable contracts.",
  formula: "contract_inbound.contract_type",
};

// ── Cost savings ─────────────────────────────────────────────────────────────

const totalReduction: Metric = {
  metric: "Total Reduction",
  period: "All available history",
  definition:
    "Auto-detected savings dollars from awarded sourcing events (RFP / RFQ / Auction). Aggregated from gold.fact_cost_savings.",
  formula: "SUM(savings_amount_usd) on fact_cost_savings",
  filters:
    "Note: baseline_amount in fact_cost_savings is back-calculated by event_type rate; treat as directional, not auditable.",
};

const totalAvoidance: Metric = {
  metric: "Total Avoidance (Approved)",
  period: "All available history",
  definition:
    "Manually attested cost-avoidance dollars (negotiated price holds, supplier consolidation, etc.) that have been approved by a reviewer. Pending entries are tracked separately.",
  formula: "SUM(savings_amount_usd) on approved avoidance ledger entries",
  filters: "approved = TRUE",
};

const pendingAvoidance: Metric = {
  metric: "Pending Avoidance",
  period: "All available history",
  definition:
    "Manually attested cost-avoidance dollars awaiting reviewer approval. Excluded from headline totals until approved.",
  formula: "SUM(savings_amount_usd) where approved = FALSE AND rejected_at IS NULL",
};

const combinedSavings: Metric = {
  metric: "Combined Savings",
  period: "All available history",
  definition:
    "Total Reduction + Approved Avoidance. Pending avoidance is NOT included.",
  formula: "Total Reduction + Total Avoidance (approved)",
};

const savingsRate: Metric = {
  metric: "Savings Rate",
  period: "Per sourcing event",
  definition:
    "Savings divided by baseline. NOTE: baseline_amount is back-calculated from awarded_amount using a fixed rate per event_type (Auction 25% / RFP 18% / other 12%) in the demo dataset.",
  formula: "savings_amount_usd / baseline_amount",
};

const savingsBaseline: Metric = {
  metric: "Baseline Amount",
  period: "Per sourcing event",
  definition:
    "Reference price before negotiation. In the demo dataset this is back-calculated by event_type rate; in production it should come from sourced supplier quotes.",
  formula: "awarded_amount / (1 − savings_rate)",
};

const savingsAwarded: Metric = {
  metric: "Awarded Amount",
  period: "Per sourcing event",
  definition: "Final negotiated price awarded to the winning supplier.",
  formula: "sourcing_event.awarded_amount",
};

const savingsPctOfBudget: Metric = {
  metric: "% of Budget",
  period: "Segment × fiscal quarter",
  definition:
    "Combined savings as a share of the FP&A EXPENSE budget for the same segment and quarter.",
  formula: "(reduction + approved avoidance) / fact_fpa_budgets.amount_usd",
  filters: "account_type = 'EXPENSE'",
};

// ── Status / event pills ─────────────────────────────────────────────────────

const approvedPill: Metric = {
  metric: "Status: Approved",
  period: "Current",
  definition: "A reviewer approved this avoidance entry; it counts toward headline totals.",
  formula: "approved = TRUE",
};

const pendingPill: Metric = {
  metric: "Status: Pending",
  period: "Current",
  definition:
    "Attested but not yet reviewed. Excluded from headline totals; shown as pending sub-line on the KPI strip.",
  formula: "approved = FALSE AND rejected_at IS NULL",
};

const rejectedPill: Metric = {
  metric: "Status: Rejected",
  period: "Current",
  definition:
    "A reviewer rejected this entry. Excluded from totals. Hover the status to see the rejection reason in the cell's native title.",
  formula: "rejected_at IS NOT NULL",
};

const eventTypeAuction: Metric = {
  metric: "Event Type: Auction",
  period: "Per event",
  definition:
    "Reverse auction sourcing event. Demo savings rate fixed at 25% — back-calculated baseline, not auditable.",
};

const eventTypeRFP: Metric = {
  metric: "Event Type: RFP",
  period: "Per event",
  definition:
    "Request for Proposal sourcing event. Demo savings rate fixed at 18%.",
};

const eventTypeOther: Metric = {
  metric: "Event Type",
  period: "Per event",
  definition:
    "RFQ or other sourcing event type. Demo savings rate fixed at 12% for non-RFP/Auction events.",
};

const paymentStatusPaid: Metric = {
  metric: "Payment Status: Paid",
  period: "Current",
  definition:
    "Invoice has been paid (cash out the door). Only PAID invoices count as realized spend across this app's metrics.",
  formula: "payment_status = 'PAID'",
};

// ── Exported catalog ─────────────────────────────────────────────────────────

export const METRICS = {
  // Home
  totalSpend,
  managedSpend,
  classifiedSpend,
  contractCoverage,
  onTimePayment,
  // Suppliers
  t12mSupplierSpend,
  invoiceCount,
  avgDpo,
  measuredMaverick,
  paymentTerms,
  workingCapitalOpp,
  // Contracts
  contractCommitted,
  pctConsumed,
  expires,
  burnDown,
  contractTypePill,
  // Cost savings
  totalReduction,
  totalAvoidance,
  pendingAvoidance,
  combinedSavings,
  savingsRate,
  savingsBaseline,
  savingsAwarded,
  savingsPctOfBudget,
  // Status / event pills
  approvedPill,
  pendingPill,
  rejectedPill,
  eventTypeAuction,
  eventTypeRFP,
  eventTypeOther,
  paymentStatusPaid,
} as const;

// Convenience: resolve event_type string → the right pill content. Used by
// the Reductions table since event_type is dynamic data.
export function eventTypeMetric(eventType: string | null | undefined): Metric {
  const t = (eventType ?? "").toLowerCase();
  if (t === "auction") return eventTypeAuction;
  if (t === "rfp") return eventTypeRFP;
  return eventTypeOther;
}
