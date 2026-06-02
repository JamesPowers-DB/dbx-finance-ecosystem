import React, { useEffect, useState } from "react";
import { BurnDownChart } from "../charts/BurnDownChart";
import { getContractBurnDown, getContractInvoices, getContractPurchaseOrders } from "../api";
import { fmtUSD, fmtPct, fmtDate, fmtDays, fmtInt } from "../format";
import type { ContractRow, ContractBurnDown, ContractInvoiceRow, ContractPORow } from "../types";

const num = (v: unknown): number => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};
const DAY = 86400000;

export type Level = "high" | "med" | "low";
export const LEVEL_COLOR: Record<Level, string> = {
  high: "var(--danger)",
  med: "var(--warning)",
  low: "var(--db-green-700)",
};

export interface Risk {
  level: Level;
  tag: string;   // short chip label for the list view
  label: string; // full banner label
  verdict: string;
  elapsedPct: number | null;
  projectedAtExpiry: number | null;
  termMonths: number | null;
}

/** Renewal-risk model — the contract's place in the risk portfolio. Priority:
 * expiring → commitment exhausted → under-utilized → approaching → on track. */
export function assessRisk(row: ContractRow): Risk {
  const consumed = num(row.pct_consumed);
  const days = row.days_to_expiration;
  const eff = row.effective_date ? new Date(row.effective_date) : null;
  const exp = row.expiration_date ? new Date(row.expiration_date) : null;
  const now = Date.now();

  let elapsedPct: number | null = null;
  let termMonths: number | null = null;
  let projectedAtExpiry: number | null = null;
  if (eff && exp) {
    const termDays = (exp.getTime() - eff.getTime()) / DAY;
    termMonths = termDays > 0 ? termDays / 30.44 : null;
    const elapsed = Math.min(Math.max((now - eff.getTime()) / DAY, 0), termDays);
    elapsedPct = termDays > 0 ? (elapsed / termDays) * 100 : null;
    if (elapsedPct && elapsedPct > 0) projectedAtExpiry = (consumed / elapsedPct) * 100;
  }
  const t12m = fmtUSD(row.trailing_12m_spend, true);

  if (days != null && days < 60) {
    return { level: "high", tag: "Due soon", label: `Renewal due — ${fmtDays(days)}`, verdict: `Expires ${fmtDate(row.expiration_date)} with ${t12m} of trailing supplier spend at stake. Start the renewal now to avoid lapsing to off-contract spend.`, elapsedPct, projectedAtExpiry, termMonths };
  }
  if (consumed >= 90) {
    return { level: "high", tag: "Exhausted", label: "Commitment nearly exhausted", verdict: `${fmtPct(consumed)} of the committed value is consumed. Size up the renewal or incremental spend will run off-contract.`, elapsedPct, projectedAtExpiry, termMonths };
  }
  if (elapsedPct != null && elapsedPct > 50 && elapsedPct - consumed > 25) {
    return { level: "med", tag: "Under-used", label: "Under-utilized", verdict: `Only ${fmtPct(consumed)} consumed with ${fmtPct(elapsedPct)} of the term elapsed — tracking to ~${fmtPct(projectedAtExpiry)} at expiry. Downsize or renegotiate the commitment at renewal.`, elapsedPct, projectedAtExpiry, termMonths };
  }
  if (days != null && days < 120) {
    return { level: "med", tag: "Renew soon", label: `Renewal approaching — ${fmtDays(days)}`, verdict: `Renewal window is open (${t12m} trailing supplier spend). Review terms before the expiration date.`, elapsedPct, projectedAtExpiry, termMonths };
  }
  return { level: "low", tag: "On track", label: "On track", verdict: `${fmtPct(consumed)} consumed with ${elapsedPct != null ? fmtPct(elapsedPct) : "—"} of term elapsed. No near-term renewal action needed.`, elapsedPct, projectedAtExpiry, termMonths };
}

const monoLabel: React.CSSProperties = {
  fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)",
  textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "var(--space-2)",
};

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (<div><div style={monoLabel}>{title}</div>{children}</div>);
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "danger" | "success" | "warning" | "default" }) {
  const color = tone === "danger" ? "var(--danger)" : tone === "success" ? "var(--success)" : tone === "warning" ? "var(--warning)" : "var(--fg-1)";
  return (
    <div style={{ background: "var(--bg-canvas)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", padding: "var(--space-3)", minWidth: 120, flex: 1 }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 4 }}>{label}</div>
      <div style={{ fontFamily: "var(--font-display)", fontSize: "var(--fs-h4)", fontWeight: 700, color }}>{value}</div>
    </div>
  );
}

function Attr({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.05em" }}>{label}</div>
      <div style={{ fontSize: 13, color: "var(--fg-1)", marginTop: 2 }}>{value}</div>
    </div>
  );
}

const td: React.CSSProperties = { padding: "var(--space-2) var(--space-3)", fontSize: 12, borderBottom: "1px solid var(--border)" };
const tdMono: React.CSSProperties = { ...td, fontFamily: "var(--font-mono)" };
const thMini: React.CSSProperties = { padding: "var(--space-2) var(--space-3)", textAlign: "left", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.06em", borderBottom: "1px solid var(--border)" };

export function ContractDetail({ row }: { row: ContractRow }) {
  const [burnDown, setBurnDown] = useState<ContractBurnDown | null>(null);
  const [invoices, setInvoices] = useState<ContractInvoiceRow[] | null>(null);
  const [pos, setPOs] = useState<ContractPORow[] | null>(null);

  useEffect(() => {
    const id = row.contract_workspace_id;
    getContractBurnDown(id).then(setBurnDown).catch(() => setBurnDown(null));
    getContractInvoices(id, 6).then(setInvoices).catch(() => setInvoices([]));
    getContractPurchaseOrders(id, 6).then(setPOs).catch(() => setPOs([]));
  }, [row.contract_workspace_id]);

  const risk = assessRisk(row);
  const color = LEVEL_COLOR[risk.level];
  const consumed = num(row.pct_consumed);

  return (
    <div style={{ background: "var(--bg-subtle)", borderTop: "2px solid var(--db-lava-600)", padding: "var(--space-5)" }}>
      {/* Prominent renewal-risk banner */}
      <div style={{ borderLeft: `4px solid ${color}`, background: "var(--bg-canvas)", border: "1px solid var(--border)", borderLeftWidth: 4, borderLeftColor: color, borderRadius: "var(--radius-md)", padding: "var(--space-4)", marginBottom: "var(--space-5)" }}>
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", flexWrap: "wrap" }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700, color, textTransform: "uppercase", letterSpacing: "0.06em", border: `1px solid ${color}`, borderRadius: "var(--radius-pill)", padding: "2px 10px" }}>
            {risk.level === "high" ? "High risk" : risk.level === "med" ? "Watch" : "Low risk"}
          </span>
          <span style={{ fontSize: "var(--fs-h4)", fontWeight: 700, color: "var(--fg-1)" }}>{risk.label}</span>
        </div>
        <div style={{ fontSize: 13, color: "var(--fg-2)", marginTop: "var(--space-2)", maxWidth: 880 }}>{risk.verdict}</div>
      </div>

      {/* KPI strip */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)", marginBottom: "var(--space-5)" }}>
        <Stat label="Committed" value={fmtUSD(row.total_committed_spend, true)} />
        <Stat label="Consumed" value={fmtUSD(row.actual_spend_to_date, true)} />
        <Stat label="Consumed %" value={fmtPct(consumed)} tone={consumed > 90 ? "danger" : consumed < 30 ? "warning" : "default"} />
        <Stat label="Term elapsed" value={risk.elapsedPct != null ? fmtPct(risk.elapsedPct) : "—"} />
        <Stat label="Proj. at expiry" value={risk.projectedAtExpiry != null ? fmtPct(risk.projectedAtExpiry) : "—"} tone={risk.projectedAtExpiry != null && risk.projectedAtExpiry < 70 ? "warning" : "default"} />
        <Stat label="Days to expiry" value={fmtDays(row.days_to_expiration)} tone={(row.days_to_expiration ?? 999) < 60 ? "danger" : (row.days_to_expiration ?? 999) < 120 ? "warning" : "default"} />
        <Stat label="Supplier T12M" value={fmtUSD(row.trailing_12m_spend, true)} />
      </div>

      {/* Burn-down + contract terms */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-6)", marginBottom: "var(--space-5)" }}>
        <Section title="Burn-down — contract-scoped paid spend">
          {burnDown == null ? (
            <div style={{ fontSize: 13, color: "var(--fg-3)" }}>Loading…</div>
          ) : burnDown.points.length === 0 ? (
            <div style={{ fontSize: 13, color: "var(--fg-3)" }}>No paid invoices in this contract's window yet.</div>
          ) : (
            <BurnDownChart points={burnDown.points} committedSpend={burnDown.total_committed_spend ?? undefined} width={520} height={220} />
          )}
        </Section>
        <Section title="Contract terms">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-4)" }}>
            <Attr label="Supplier" value={row.supplier_name ?? row.supplier_id} />
            <Attr label="Type" value={row.contract_type} />
            <Attr label="Region" value={row.region ?? "—"} />
            <Attr label="Term" value={risk.termMonths != null ? `${risk.termMonths.toFixed(0)} months` : "—"} />
            <Attr label="Effective" value={fmtDate(row.effective_date)} />
            <Attr label="Expires" value={fmtDate(row.expiration_date)} />
            <Attr label="Status" value={row.status} />
            <Attr label="Source system" value={row.source_system ?? "—"} />
          </div>
        </Section>
      </div>

      {/* Linked activity */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-6)" }}>
        <Section title="Linked invoices (top by amount)">
          {invoices == null ? <div style={{ fontSize: 13, color: "var(--fg-3)" }}>Loading…</div> : invoices.length === 0 ? (
            <div style={{ fontSize: 13, color: "var(--fg-3)" }}>No paid invoices in this contract window.</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead><tr><th style={thMini}>Date</th><th style={{ ...thMini, textAlign: "right" }}>Amount</th><th style={thMini}>Category</th></tr></thead>
              <tbody>
                {invoices.map((i) => (
                  <tr key={i.invoice_line_id}>
                    <td style={tdMono}>{fmtDate(i.invoice_date)}</td>
                    <td style={{ ...tdMono, textAlign: "right" }}>{fmtUSD(i.amount, true)}</td>
                    <td style={td}>{(i.true_category_primary ?? "—").replace(/_/g, " ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Section>
        <Section title="Linked purchase orders (top by amount)">
          {pos == null ? <div style={{ fontSize: 13, color: "var(--fg-3)" }}>Loading…</div> : pos.length === 0 ? (
            <div style={{ fontSize: 13, color: "var(--fg-3)" }}>No POs in this contract window.</div>
          ) : (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead><tr><th style={thMini}>PO #</th><th style={thMini}>Line</th><th style={{ ...thMini, textAlign: "right" }}>Amount</th><th style={thMini}>Category</th></tr></thead>
              <tbody>
                {pos.map((p, i) => (
                  <tr key={`${p.po_number}-${p.po_line_num}-${i}`}>
                    <td style={{ ...tdMono, maxWidth: 130, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{p.po_number}</td>
                    <td style={tdMono}>{fmtInt(p.po_line_num)}</td>
                    <td style={{ ...tdMono, textAlign: "right" }}>{fmtUSD(p.extended_amount, true)}</td>
                    <td style={td}>{(p.true_category_primary ?? "—").replace(/_/g, " ")}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Section>
      </div>
    </div>
  );
}
