import React, { useEffect, useState } from "react";
import { BlobBg } from "../components/layout/BlobBg";
import { PageHero } from "../components/layout/PageHero";
import { Card } from "../components/layout/Card";
import { Pill, SegSelect } from "../components/Buttons";
import { getSuppliers, getRenegotiationTargets } from "../api";
import { fmtUSD, fmtPct, fmtInt } from "../format";
import type { RenegotiationTarget, SupplierRow } from "../types";

export function Suppliers({ searchQuery = "" }: { searchQuery?: string }) {
  const [suppliers, setSuppliers] = useState<SupplierRow[]>([]);
  const [targets, setTargets] = useState<RenegotiationTarget[]>([]);
  const [view, setView] = useState<"scorecard" | "targets">("scorecard");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      getSuppliers({ sort_by: "trailing_12m_spend", exclude_regulated: "true" }),
      getRenegotiationTargets(),
    ])
      .then(([s, t]) => { setSuppliers(s); setTargets(t); })
      .finally(() => setLoading(false));
  }, []);

  const q = searchQuery.toLowerCase();
  const filteredSuppliers = q
    ? suppliers.filter(
        (s) =>
          s.supplier_name?.toLowerCase().includes(q) ||
          s.category_primary?.toLowerCase().includes(q) ||
          s.region?.toLowerCase().includes(q) ||
          s.payment_terms?.toLowerCase().includes(q),
      )
    : suppliers;
  const filteredTargets = q
    ? targets.filter(
        (t) =>
          t.supplier_name?.toLowerCase().includes(q) ||
          t.category_primary?.toLowerCase().includes(q) ||
          t.current_payment_terms?.toLowerCase().includes(q),
      )
    : targets;

  return (
    <div style={{ position: "relative", flex: 1, overflow: "auto", padding: "var(--space-6)" }}>
      <BlobBg />
      <div style={{ position: "relative", zIndex: 1, maxWidth: 1200 }}>
        <PageHero
          eyebrow="Review"
          title="Supplier Performance"
          subtitle="Trailing 12-month scorecard and payment-terms renegotiation targets. Regulated suppliers excluded from targets."
          right={
            <SegSelect
              options={[
                { label: "Scorecard", value: "scorecard" },
                { label: "Renegotiation Targets", value: "targets" },
              ]}
              value={view}
              onChange={(v) => setView(v as "scorecard" | "targets")}
            />
          }
        />

        {view === "scorecard" && (
          <Card padding="0">
            {loading ? (
              <div style={{ padding: "var(--space-7)", textAlign: "center", color: "var(--fg-3)" }}>Loading…</div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      {["Supplier", "Category", "Region", "T12M Spend", "Invoices", "On-Time %", "Avg DPO", "Terms", "Maverick"].map((h) => (
                        <th key={h} style={{ padding: "var(--space-3) var(--space-4)", textAlign: "left",
                          fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)",
                          fontWeight: 500, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredSuppliers.map((s) => (
                      <tr key={s.supplier_id} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontSize: 13, fontWeight: 500 }}>
                          {s.supplier_name ?? s.supplier_id}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)" }}>
                          <Pill>{s.category_primary ?? "—"}</Pill>
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontSize: 12, color: "var(--fg-2)" }}>
                          {s.region ?? "—"}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                          {fmtUSD(s.trailing_12m_spend, true)}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                          {fmtInt(s.invoice_count)}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12,
                          color: (s.on_time_payment_pct ?? 0) < 80 ? "var(--danger)" : "var(--success)" }}>
                          {fmtPct(s.on_time_payment_pct)}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                          {s.avg_dpo != null ? `${Number(s.avg_dpo).toFixed(1)}d` : "—"}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)" }}>
                          <Pill>{s.payment_terms ?? "—"}</Pill>
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)" }}>
                          {/* Maverick strip plot: dot position */}
                          <div style={{ position: "relative", width: 80, height: 12 }}>
                            <div style={{ position: "absolute", top: 5, left: 0, right: 0, height: 2,
                              background: "var(--border)", borderRadius: 1 }} />
                            <div style={{
                              position: "absolute",
                              top: 2,
                              left: `${(s.maverick_propensity ?? 0) * 100 / 0.3}%`,
                              width: 8, height: 8, borderRadius: "50%",
                              background: (s.maverick_propensity ?? 0) > 0.15 ? "var(--danger)" : "var(--db-navy-800)",
                              transform: "translateX(-50%)",
                            }} />
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        )}

        {view === "targets" && (
          <Card padding="0">
            {loading ? (
              <div style={{ padding: "var(--space-7)", textAlign: "center", color: "var(--fg-3)" }}>Loading…</div>
            ) : (
              <div style={{ overflowX: "auto" }}>
                <div style={{ padding: "var(--space-4)", borderBottom: "1px solid var(--border)" }}>
                  <p style={{ fontSize: "var(--fs-body-sm)", color: "var(--fg-2)" }}>
                    Ranked by working-capital opportunity from extending payment terms to Net60.
                    Regulated suppliers are excluded.
                  </p>
                </div>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      {["Supplier", "Category", "T12M Spend", "Current Terms", "Current DPO", "Target DPO", "WC Opportunity"].map((h) => (
                        <th key={h} style={{ padding: "var(--space-3) var(--space-4)", textAlign: "left",
                          fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)",
                          fontWeight: 500, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredTargets.map((t) => (
                      <tr key={t.supplier_id} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontSize: 13, fontWeight: 500 }}>
                          {t.supplier_name ?? t.supplier_id}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)" }}>
                          <Pill>{t.category_primary ?? "—"}</Pill>
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                          {fmtUSD(t.trailing_12m_spend, true)}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)" }}>
                          <Pill>{t.current_payment_terms ?? "—"}</Pill>
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                          {t.current_dpo != null ? `${Number(t.current_dpo).toFixed(1)}d` : "—"}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12,
                          color: "var(--db-lava-600)", fontWeight: 600 }}>
                          {t.target_dpo}d
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 13,
                          fontWeight: 700, color: "var(--success)" }}>
                          {fmtUSD(t.working_capital_opportunity_usd, true)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        )}
      </div>
    </div>
  );
}
