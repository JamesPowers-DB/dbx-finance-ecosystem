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
    "Share of addressable paid spend that is linked to procurement governance — either flagged as PO-matched (3-way match) or covered by an active SOW/Framework contract for the same supplier inside the contract's effective window.",
  formula:
    "SUM(addressable spend where po_matched_flag = 'Y' OR active contract matched) / SUM(addressable spend)",
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
    "Share of addressable paid spend that landed against an active contract for the supplier inside the contract's effective–expiration window.",
  formula:
    "SUM(paid invoices matched to active contract) / SUM(addressable paid spend), same T12M window",
  filters:
    "payment_status = 'PAID' AND addressability = 'Addressable' AND contract.status = 'Active'",
};

const onTimePayment: Metric = {
  metric: "On-Time Payment %",
  period: "Trailing 12 months",
  definition:
    "Spend-weighted percentage of paid invoices where the payment date was on or before the due date. Helios paying suppliers on time — not supplier delivery OTD.",
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
    "Average days-to-pay across the supplier's paid invoices. Lower than current payment terms means Helios is paying early.",
  formula: "AVG(days_to_pay) on PAID invoices",
  filters: "payment_status = 'PAID' AND invoice_date in T12M",
};

const measuredMaverick: Metric = {
  metric: "Maverick Spend %",
  period: "Trailing 12 months",
  definition:
    "Share of the supplier's T12M paid spend that did NOT land against an active contract for them (off-contract leakage). Observed measure — replaces the prior synthetic propensity seed.",
  formula:
    "SUM(amount not matched to active contract) / SUM(amount), supplier-scoped",
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

// ── Labeling monitor ─────────────────────────────────────────────────────────

const coveragePct: Metric = {
  metric: "Coverage %",
  period: "Per segment × fiscal quarter",
  definition:
    "Share of invoice lines that received an ML-predicted secondary category in this period.",
  formula: "classified_lines / total_lines",
};

const avgCoverage: Metric = {
  metric: "Avg Coverage",
  period: "All loaded periods",
  definition:
    "Average classification coverage across all segment × quarter buckets currently loaded.",
  formula: "AVG(coverage_pct) across coverage rows",
};

const totalClassified: Metric = {
  metric: "Total Classified",
  period: "All loaded periods",
  definition:
    "Total invoice line count with a predicted secondary category across all loaded periods.",
  formula: "SUM(classified_lines)",
};

const totalLinesM: Metric = {
  metric: "Total Lines",
  period: "All loaded periods",
  definition: "Total invoice line count (classified + unclassified).",
  formula: "SUM(total_lines)",
};

const disagreementsM: Metric = {
  metric: "Disagreements",
  period: "Latest inference run",
  definition:
    "Count of invoice lines where the ML-predicted secondary category disagrees with the ground-truth label.",
  formula: "COUNT(*) where true_category_secondary != predicted_secondary_category",
};

const confidenceLeaf: Metric = {
  metric: "Confidence (Leaf)",
  period: "Latest inference run",
  definition:
    "Distribution of secondary_confidence scores across classified invoice lines. Dashed line at 0.75 marks the managed-spend threshold.",
  formula: "Histogram of secondary_confidence in 10 buckets",
};

const confidenceParent: Metric = {
  metric: "Confidence (Parent)",
  period: "Latest inference run",
  definition:
    "Distribution of primary_confidence scores across classified invoice lines.",
  formula: "Histogram of primary_confidence in 10 buckets",
};

const holdoutAccuracy: Metric = {
  metric: "Holdout Leaf Accuracy",
  period: "Per eval run",
  definition:
    "Accuracy of leaf (secondary-category) prediction on the held-out evaluation set.",
  formula: "correct_leaf / eval_rows on holdout split",
};

const maverickAccuracy: Metric = {
  metric: "Maverick Leaf Accuracy",
  period: "Per eval run",
  definition:
    "Leaf accuracy on the maverick-spend slice — invoices labeled with categories that disagree with the supplier's typical category. Stress test for the classifier.",
  formula: "correct_leaf / eval_rows on maverick split",
};

const parentAccuracy: Metric = {
  metric: "Holdout Parent Accuracy",
  period: "Per eval run",
  definition: "Accuracy of parent (primary-category) prediction on the held-out evaluation set.",
  formula: "correct_parent / eval_rows on holdout split",
};

const secondaryConfidenceCol: Metric = {
  metric: "Secondary Confidence",
  period: "Latest inference run",
  definition:
    "Model's confidence score for the predicted secondary category on this line. Below 0.50 is colored red as a review prompt.",
  formula: "Model softmax output for the leaf class",
};

const predictedSecondaryCol: Metric = {
  metric: "Predicted Secondary",
  period: "Latest inference run",
  definition:
    "Leaf category the classifier predicted for this invoice line. Disagreements with the true label are surfaced here for triage.",
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
  // Labeling
  coveragePct,
  avgCoverage,
  totalClassified,
  totalLines: totalLinesM,
  disagreements: disagreementsM,
  confidenceLeaf,
  confidenceParent,
  holdoutAccuracy,
  maverickAccuracy,
  parentAccuracy,
  secondaryConfidenceCol,
  predictedSecondaryCol,
} as const;

// Convenience: resolve event_type string → the right pill content. Used by
// the Reductions table since event_type is dynamic data.
export function eventTypeMetric(eventType: string | null | undefined): Metric {
  const t = (eventType ?? "").toLowerCase();
  if (t === "auction") return eventTypeAuction;
  if (t === "rfp") return eventTypeRFP;
  return eventTypeOther;
}
