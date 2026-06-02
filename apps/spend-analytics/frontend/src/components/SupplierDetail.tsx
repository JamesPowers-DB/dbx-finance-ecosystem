import React from "react";
import { BarChart } from "../charts/BarChart";
import { LineChart } from "../charts/LineChart";
import { RenegotiationModel } from "./RenegotiationModel";
import { fmtUSD, fmtPct, fmtInt, fmtDate, fmtDays } from "../format";
import type { SupplierScorecard } from "../types";

const num = (v: unknown): number => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};

const monoLabel: React.CSSProperties = {
  fontFamily: "var(--font-mono)",
  fontSize: 11,
  color: "var(--fg-3)",
  textTransform: "uppercase",
  letterSpacing: "0.06em",
  marginBottom: "var(--space-2)",
};

function Section({ title, children, span }: { title: string; children: React.ReactNode; span?: boolean }) {
  return (
    <div style={{ gridColumn: span ? "1 / -1" : undefined }}>
      <div style={monoLabel}>{title}</div>
      {children}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: "danger" | "success" | "default" }) {
  const color = tone === "danger" ? "var(--danger)" : tone === "success" ? "var(--success)" : "var(--fg-1)";
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

export function SupplierDetail({ s }: { s: SupplierScorecard }) {
  const a = s.attributes ?? ({} as SupplierScorecard["attributes"]);
  const clf = s.classification_summary ?? ({} as SupplierScorecard["classification_summary"]);
  const descriptor = [a.category_primary, a.region].filter(Boolean).join(" · ");

  return (
    <div style={{ background: "var(--bg-subtle)", borderTop: "2px solid var(--db-navy-800)", padding: "var(--space-5)" }}>
      {/* Attributes strip */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-6)", alignItems: "flex-start", marginBottom: "var(--space-2)" }}>
        <Attr label="Location" value={`${a.region ?? "—"}${a.country_code ? ` · ${a.country_code}` : ""}`} />
        <Attr label="Supplier since" value={fmtDate(a.created_date)} />
        <Attr label="Category" value={a.category_primary ?? "—"} />
        <Attr label="Terms" value={a.payment_terms ?? s.payment_terms ?? "—"} />
        {num(a.aliases_resolved) > 1 && (
          <Attr label="Entity-resolved from" value={`${fmtInt(a.aliases_resolved)} source records`} />
        )}
        {a.is_regulated_supplier && (
          <span style={{ alignSelf: "center", fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 600, color: "var(--db-yellow-600)", border: "1px solid var(--db-yellow-600)", borderRadius: "var(--radius-pill)", padding: "1px 8px" }}>
            REGULATED
          </span>
        )}
      </div>
      {descriptor && <div style={{ fontSize: 13, color: "var(--fg-2)", marginBottom: "var(--space-4)" }}>{descriptor}</div>}

      {/* KPI strip */}
      <div style={{ display: "flex", flexWrap: "wrap", gap: "var(--space-2)", marginBottom: "var(--space-5)" }}>
        <Stat label="T12M Spend" value={fmtUSD(s.trailing_12m_spend, true)} />
        <Stat label="Invoices" value={fmtInt(s.invoice_count)} />
        <Stat label="On-Time Pay %" value={fmtPct(s.on_time_payment_pct)} tone={(s.on_time_payment_pct ?? 0) < 80 ? "danger" : "success"} />
        <Stat label="Avg DPO" value={s.avg_dpo != null ? `${Number(s.avg_dpo).toFixed(1)}d` : "—"} />
        <Stat label="Maverick %" value={fmtPct(s.measured_maverick_pct)} tone={(s.measured_maverick_pct ?? 0) > 15 ? "danger" : "default"} />
        <Stat label="Managed $" value={fmtUSD(s.economics?.managed_spend, true)} />
      </div>

      {/* Row: classification + spend over time */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-6)", marginBottom: "var(--space-5)" }}>
        <Section title="Spend classification — ML model">
          <div style={{ display: "flex", gap: "var(--space-2)", marginBottom: "var(--space-3)" }}>
            <Stat label="Predicted = True" value={fmtPct(clf.agreement_pct)} tone={(clf.agreement_pct ?? 0) >= 90 ? "success" : "default"} />
            <Stat label="Classified" value={fmtPct(clf.classified_pct)} />
            <Stat label="Avg confidence" value={fmtPct(clf.avg_confidence == null ? null : num(clf.avg_confidence) * 100)} />
          </div>
          {s.classification_mix?.length > 0 ? (
            <BarChart
              data={s.classification_mix.map((c) => ({ label: (c.category ?? "Unknown").replace(/_/g, " "), value: num(c.spend_usd) }))}
              color="var(--db-navy-800)"
              formatValue={(v) => fmtUSD(v, true)}
              width={480}
              height={Math.max(140, s.classification_mix.length * 30)}
            />
          ) : (
            <div style={{ fontSize: 13, color: "var(--fg-3)" }}>No classified spend.</div>
          )}
        </Section>

        <Section title="Spend over time — paid, last 8 quarters">
          {s.spend_trend?.length >= 2 ? (
            <LineChart
              points={s.spend_trend.map((q) => ({
                label: `FY${String(q.fiscal_year).slice(-2)} Q${q.fiscal_quarter}`,
                value: num(q.spend_usd),
              }))}
              width={480}
              height={170}
            />
          ) : (
            <div style={{ fontSize: 13, color: "var(--fg-3)" }}>Not enough quarterly data.</div>
          )}
        </Section>
      </div>

      {/* Row: category breakdown + top commitments */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-6)", marginBottom: "var(--space-5)" }}>
        <Section title="Spend by category (T12M)">
          {s.category_breakdown?.length > 0 ? (
            <BarChart
              data={s.category_breakdown.slice(0, 6).map((c) => ({ label: (c.category ?? "Unknown").replace(/_/g, " "), value: num(c.spend_usd) }))}
              color="var(--db-lava-600)"
              formatValue={(v) => fmtUSD(v, true)}
              width={480}
              height={Math.max(140, Math.min(s.category_breakdown.length, 6) * 30)}
            />
          ) : (
            <div style={{ fontSize: 13, color: "var(--fg-3)" }}>No T12M paid spend.</div>
          )}
        </Section>

        <Section title="Top spend commitments — purchase orders">
          {s.top_commitments?.length > 0 ? (
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr>
                  <th style={thMini}>PO</th>
                  <th style={thMini}>Date</th>
                  <th style={{ ...thMini, textAlign: "right" }}>Committed</th>
                  <th style={thMini}>Status</th>
                  <th style={thMini}>Sourcing</th>
                </tr>
              </thead>
              <tbody>
                {s.top_commitments.map((c) => (
                  <tr key={c.po_number}>
                    <td style={{ ...tdMono, maxWidth: 130, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.po_number}</td>
                    <td style={tdMono}>{fmtDate(c.po_date)}</td>
                    <td style={{ ...tdMono, textAlign: "right" }}>{fmtUSD(num(c.committed_usd), true)}</td>
                    <td style={td}>{c.po_status ?? "—"}</td>
                    <td style={td}>
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: c.on_contract ? "var(--db-green-700)" : "var(--db-lava-600)" }}>
                        {c.on_contract ? "on contract" : "off-contract"}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div style={{ fontSize: 13, color: "var(--fg-3)" }}>No recent purchase orders.</div>
          )}
        </Section>
      </div>

      {/* Active contracts */}
      <Section title="Active contracts" span>
        {s.contracts?.length > 0 ? (
          <table style={{ width: "100%", borderCollapse: "collapse", marginBottom: "var(--space-5)" }}>
            <thead>
              <tr>
                <th style={thMini}>Title</th>
                <th style={thMini}>Type</th>
                <th style={{ ...thMini, textAlign: "right" }}>Committed</th>
                <th style={{ ...thMini, textAlign: "right" }}>Used</th>
                <th style={thMini}>Expires</th>
              </tr>
            </thead>
            <tbody>
              {s.contracts.map((c) => (
                <tr key={c.contract_workspace_id}>
                  <td style={{ ...td, maxWidth: 280, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{c.title}</td>
                  <td style={td}>{c.contract_type}</td>
                  <td style={{ ...tdMono, textAlign: "right" }}>{fmtUSD(c.total_committed_spend, true)}</td>
                  <td style={{ ...tdMono, textAlign: "right", color: (c.pct_consumed ?? 0) > 90 ? "var(--danger)" : "var(--fg-1)" }}>{fmtPct(c.pct_consumed)}</td>
                  <td style={tdMono}>{fmtDate(c.expiration_date)}{c.days_to_expiration != null ? ` (${fmtDays(c.days_to_expiration)})` : ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div style={{ fontSize: 13, color: "var(--fg-3)", marginBottom: "var(--space-5)" }}>No currently active contracts.</div>
        )}
      </Section>

      {/* Renegotiation what-if */}
      <div style={{ borderTop: "1px solid var(--border)", paddingTop: "var(--space-4)" }}>
        <RenegotiationModel economics={s.economics ?? {}} avgDpo={s.avg_dpo} paymentTerms={s.payment_terms} />
      </div>
    </div>
  );
}
