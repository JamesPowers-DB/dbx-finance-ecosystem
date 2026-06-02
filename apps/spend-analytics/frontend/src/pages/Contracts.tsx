import React, { useEffect, useMemo, useState } from "react";
import { BlobBg } from "../components/layout/BlobBg";
import { PageHero } from "../components/layout/PageHero";
import { Card } from "../components/layout/Card";
import { Pill } from "../components/Buttons";
import { MetricTooltip } from "../components/MetricTooltip";
import { HeaderLabel } from "../components/HeaderLabel";
import { METRICS } from "../components/metricDefinitions";
import { ContractDetail, assessRisk, LEVEL_COLOR } from "../components/ContractDetail";
import { getContracts } from "../api";
import { fmtUSD, fmtPct, fmtDate, fmtDays } from "../format";
import type { ContractRow } from "../types";

const COLUMNS = [
  { label: "Supplier" },
  { label: "Type" },
  { label: "Title" },
  { label: "Renewal Risk" },
  { label: "Committed", tooltip: METRICS.contractCommitted },
  { label: "Consumed", tooltip: METRICS.pctConsumed },
  { label: "Expires", tooltip: METRICS.expires },
];

const cell: React.CSSProperties = { padding: "var(--space-3) var(--space-4)" };

// High-risk first so the renewal portfolio surfaces at the top.
const RISK_ORDER: Record<string, number> = { high: 0, med: 1, low: 2 };

export function Contracts({ searchQuery = "" }: { searchQuery?: string }) {
  const [contracts, setContracts] = useState<ContractRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    getContracts()
      .then(setContracts)
      .finally(() => setLoading(false));
  }, []);

  const q = searchQuery.toLowerCase();
  const rows = useMemo(() => {
    const filtered = q
      ? contracts.filter(
          (c) =>
            c.supplier_name?.toLowerCase().includes(q) ||
            c.title?.toLowerCase().includes(q) ||
            c.contract_type?.toLowerCase().includes(q) ||
            c.region?.toLowerCase().includes(q),
        )
      : contracts;
    // Sort by renewal risk so the portfolio risk leads.
    return [...filtered]
      .map((c) => ({ c, risk: assessRisk(c) }))
      .sort((a, b) => RISK_ORDER[a.risk.level] - RISK_ORDER[b.risk.level] || (a.c.days_to_expiration ?? 9999) - (b.c.days_to_expiration ?? 9999));
  }, [contracts, q]);

  const highCount = rows.filter((r) => r.risk.level === "high").length;

  return (
    <div style={{ position: "relative", flex: 1, overflow: "auto", padding: "var(--space-6)" }}>
      <BlobBg />
      <div style={{ position: "relative", zIndex: 1, maxWidth: 1280 }}>
        <PageHero
          eyebrow="Review"
          title="Contracts"
          subtitle="Active contracts ranked by renewal risk — expiring soon, under-utilized, or near exhaustion. Click a contract to expand its burn-down, terms, and linked activity."
          right={
            highCount > 0 ? (
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-caption)", color: "var(--danger)", border: "1px solid var(--danger)", borderRadius: "var(--radius-pill)", padding: "4px 12px" }}>
                {highCount} need attention
              </span>
            ) : undefined
          }
        />

        <Card padding="0">
          {loading ? (
            <div style={{ padding: "var(--space-7)", textAlign: "center", color: "var(--fg-3)" }}>Loading…</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ minWidth: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)" }}>
                    {COLUMNS.map((h) => (
                      <th key={h.label} style={{ ...cell, textAlign: "left", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", fontWeight: 500, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                        <HeaderLabel label={h.label} tooltip={h.tooltip} />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map(({ c, risk }) => {
                    const isOpen = selected === c.contract_workspace_id;
                    const riskColor = LEVEL_COLOR[risk.level];
                    const urgency = (c.days_to_expiration ?? 999) < 60 ? "var(--danger)" : (c.days_to_expiration ?? 999) < 120 ? "var(--warning)" : "var(--fg-1)";
                    return (
                      <React.Fragment key={c.contract_workspace_id}>
                        <tr
                          onClick={() => setSelected(isOpen ? null : c.contract_workspace_id)}
                          style={{
                            borderBottom: isOpen ? "none" : "1px solid var(--border)",
                            background: isOpen ? "var(--bg-subtle)" : "transparent",
                            cursor: "pointer",
                          }}
                        >
                          <td style={{ ...cell, fontSize: 13, color: isOpen ? "var(--db-lava-600)" : undefined, fontWeight: isOpen ? 600 : 400 }}>
                            {c.supplier_name ?? c.supplier_id}
                          </td>
                          <td style={cell}>
                            <MetricTooltip content={METRICS.contractTypePill} hoverOnly>
                              <Pill active={false}>{c.contract_type}</Pill>
                            </MetricTooltip>
                          </td>
                          <td style={{ ...cell, fontSize: 13, maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            {c.title}
                          </td>
                          <td style={cell}>
                            <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 600, color: riskColor, border: `1px solid ${riskColor}`, borderRadius: "var(--radius-pill)", padding: "2px 9px", whiteSpace: "nowrap" }}>
                              {risk.tag}
                            </span>
                          </td>
                          <td style={{ ...cell, fontFamily: "var(--font-mono)", fontSize: 12 }}>
                            {fmtUSD(c.total_committed_spend, true)}
                          </td>
                          <td style={cell}>
                            <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                              <div style={{ width: 60, height: 6, background: "var(--bg-subtle)", borderRadius: 3 }}>
                                <div style={{ width: `${Math.min(c.pct_consumed ?? 0, 100)}%`, height: "100%", background: (c.pct_consumed ?? 0) > 90 ? "var(--danger)" : "var(--db-lava-600)", borderRadius: 3 }} />
                              </div>
                              <span style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>{fmtPct(c.pct_consumed)}</span>
                            </div>
                          </td>
                          <td style={{ ...cell, fontFamily: "var(--font-mono)", fontSize: 12, color: urgency }}>
                            {fmtDate(c.expiration_date)} ({fmtDays(c.days_to_expiration)})
                          </td>
                        </tr>
                        {isOpen && (
                          <tr style={{ borderBottom: "1px solid var(--border)" }}>
                            <td colSpan={COLUMNS.length} style={{ padding: 0 }}>
                              <ContractDetail row={c} />
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                  {rows.length === 0 && (
                    <tr><td colSpan={COLUMNS.length} style={{ ...cell, color: "var(--fg-3)" }}>No contracts match.</td></tr>
                  )}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
