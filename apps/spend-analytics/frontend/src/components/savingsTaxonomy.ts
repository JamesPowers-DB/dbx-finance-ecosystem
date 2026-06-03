import type { SavingsClass } from "../types";

// Savings type taxonomy — must stay in lockstep with the backend
// cost_savings.SAVINGS_TYPES (key + class). Labels are display-facing.
export interface SavingsTypeDef {
  key: string;
  cls: SavingsClass;
  label: string;
}

export const SAVINGS_TYPES: SavingsTypeDef[] = [
  // Cost Reduction (hard savings)
  { key: "unit_price_reduction", cls: "reduction", label: "Unit price reduction vs. prior contract/PO" },
  { key: "renegotiation",        cls: "reduction", label: "Renegotiation of existing contract (mid-term decrease)" },
  { key: "competitive_bid",      cls: "reduction", label: "Competitive bid / reverse auction below incumbent" },
  { key: "rebates_volume",       cls: "reduction", label: "Rebates & volume discounts captured" },
  { key: "spec_demand",          cls: "reduction", label: "Specification change or demand reduction" },
  // Cost Avoidance (soft savings)
  { key: "below_quote",          cls: "avoidance", label: "Negotiated below initial supplier quote" },
  { key: "avoided_increase",     cls: "avoidance", label: "Avoided supplier price increase" },
  { key: "held_flat",            cls: "avoidance", label: "Held price flat vs. inflation / market index" },
  { key: "below_should_cost",    cls: "avoidance", label: "New-buy below should-cost / benchmark" },
  { key: "value_adds",           cls: "avoidance", label: "Value-adds at no cost (freight, warranty, SLAs)" },
];

export const SAVINGS_TYPE_LABEL: Record<string, string> = Object.fromEntries(
  SAVINGS_TYPES.map((t) => [t.key, t.label]),
);

export const CLASS_LABEL: Record<SavingsClass, string> = {
  reduction: "Cost Reduction",
  avoidance: "Cost Avoidance",
};
