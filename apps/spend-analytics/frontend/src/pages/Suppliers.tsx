import React, { useEffect, useMemo, useRef, useState } from "react";
import { BlobBg } from "../components/layout/BlobBg";
import { PageHero } from "../components/layout/PageHero";
import { Card } from "../components/layout/Card";
import { Pill } from "../components/Buttons";
import { MetricTooltip } from "../components/MetricTooltip";
import { HeaderLabel } from "../components/HeaderLabel";
import { METRICS } from "../components/metricDefinitions";
import { SupplierDetail } from "../components/SupplierDetail";
import { getSuppliers, getSupplierScorecard } from "../api";
import { fmtUSD, fmtPct, fmtInt } from "../format";
import type { SupplierRow, SupplierScorecard } from "../types";

const COLUMNS = [
  { label: "Supplier" },
  { label: "Category" },
  { label: "Region" },
  { label: "T12M Spend", tooltip: METRICS.t12mSupplierSpend },
  { label: "Invoices", tooltip: METRICS.invoiceCount },
  { label: "On-Time Payment %", tooltip: METRICS.onTimePayment },
  { label: "Avg DPO", tooltip: METRICS.avgDpo },
  { label: "Terms", tooltip: METRICS.paymentTerms },
  { label: "Maverick", tooltip: METRICS.measuredMaverick },
];

const cell: React.CSSProperties = { padding: "var(--space-3) var(--space-4)" };

export function Suppliers({ searchQuery = "", focusSupplierId = null }: { searchQuery?: string; focusSupplierId?: string | null }) {
  const [suppliers, setSuppliers] = useState<SupplierRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [scorecard, setScorecard] = useState<SupplierScorecard | null>(null);
  const [scoreLoading, setScoreLoading] = useState(false);
  const selectedRowRef = useRef<HTMLTableRowElement | null>(null);

  useEffect(() => {
    getSuppliers({ sort_by: "trailing_12m_spend", exclude_regulated: "true" })
      .then(setSuppliers)
      .finally(() => setLoading(false));
  }, []);

  // Deep-link from another page (e.g. Analytics): open that supplier's row.
  useEffect(() => {
    if (focusSupplierId) setSelectedId(focusSupplierId);
  }, [focusSupplierId]);

  // Lazy-load the scorecard whenever the open row changes.
  useEffect(() => {
    if (!selectedId) {
      setScorecard(null);
      return;
    }
    setScoreLoading(true);
    setScorecard(null);
    getSupplierScorecard(selectedId)
      .then(setScorecard)
      .catch(() => setScorecard(null))
      .finally(() => setScoreLoading(false));
  }, [selectedId]);

  // Bring the opened row into view (esp. for deep-links from other pages).
  useEffect(() => {
    if (selectedId && selectedRowRef.current) {
      selectedRowRef.current.scrollIntoView({ block: "center", behavior: "smooth" });
    }
  }, [selectedId, suppliers]);

  const q = searchQuery.toLowerCase();
  const filteredSuppliers = useMemo(
    () =>
      q
        ? suppliers.filter(
            (s) =>
              s.supplier_name?.toLowerCase().includes(q) ||
              s.category_primary?.toLowerCase().includes(q) ||
              s.region?.toLowerCase().includes(q) ||
              s.payment_terms?.toLowerCase().includes(q),
          )
        : suppliers,
    [suppliers, q],
  );

  return (
    <div style={{ position: "relative", flex: 1, overflow: "auto", padding: "var(--space-6)" }}>
      <BlobBg />
      <div style={{ position: "relative", zIndex: 1, maxWidth: 1280 }}>
        <PageHero
          eyebrow="Review"
          title="Supplier Performance"
          subtitle="Trailing 12-month paid-spend scorecard. Click a supplier to expand its full profile — ML classification, spend history, commitments, contracts, and a renegotiation what-if. Regulated suppliers excluded."
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
                  {filteredSuppliers.map((s) => {
                    const isMaverick = (s.measured_maverick_pct ?? 0) > 15.0;
                    const dotPct = Math.min((s.measured_maverick_pct ?? 0) / 30.0, 1) * 100;
                    const isOpen = selectedId === s.supplier_id;
                    return (
                      <React.Fragment key={s.supplier_id}>
                        <tr
                          ref={isOpen ? selectedRowRef : undefined}
                          onClick={() => setSelectedId(isOpen ? null : s.supplier_id)}
                          style={{
                            borderBottom: isOpen ? "none" : "1px solid var(--border)",
                            background: isOpen ? "var(--bg-subtle)" : "transparent",
                            cursor: "pointer",
                          }}
                        >
                          <td style={{ ...cell, fontSize: 13, fontWeight: 500, color: isOpen ? "var(--db-lava-600)" : undefined }}>
                            {s.supplier_name ?? s.supplier_id}
                          </td>
                          <td style={cell}><Pill>{s.category_primary ?? "—"}</Pill></td>
                          <td style={{ ...cell, fontSize: 12, color: "var(--fg-2)" }}>{s.region ?? "—"}</td>
                          <td style={{ ...cell, fontFamily: "var(--font-mono)", fontSize: 12 }}>{fmtUSD(s.trailing_12m_spend, true)}</td>
                          <td style={{ ...cell, fontFamily: "var(--font-mono)", fontSize: 12 }}>{fmtInt(s.invoice_count)}</td>
                          <td style={{ ...cell, fontFamily: "var(--font-mono)", fontSize: 12, color: (s.on_time_payment_pct ?? 0) < 80 ? "var(--danger)" : "var(--success)" }}>{fmtPct(s.on_time_payment_pct)}</td>
                          <td style={{ ...cell, fontFamily: "var(--font-mono)", fontSize: 12 }}>{s.avg_dpo != null ? `${Number(s.avg_dpo).toFixed(1)}d` : "—"}</td>
                          <td style={cell}><Pill>{s.payment_terms ?? "—"}</Pill></td>
                          <td style={cell}>
                            <MetricTooltip
                              content={{ ...METRICS.measuredMaverick, metric: `${METRICS.measuredMaverick.metric} — ${fmtPct(s.measured_maverick_pct)}` }}
                              placement="bottom-right"
                              hoverOnly
                            >
                              <div style={{ position: "relative", width: 80, height: 12, cursor: "help" }}>
                                <div style={{ position: "absolute", top: 5, left: 0, right: 0, height: 2, background: "var(--border)", borderRadius: 1 }} />
                                <div style={{ position: "absolute", top: 2, left: `${dotPct}%`, width: 8, height: 8, borderRadius: "50%", background: isMaverick ? "var(--danger)" : "var(--db-navy-800)", transform: "translateX(-50%)" }} />
                              </div>
                            </MetricTooltip>
                          </td>
                        </tr>
                        {isOpen && (
                          <tr style={{ borderBottom: "1px solid var(--border)" }}>
                            <td colSpan={COLUMNS.length} style={{ padding: 0 }}>
                              {scoreLoading || !scorecard ? (
                                <div style={{ padding: "var(--space-6)", textAlign: "center", color: "var(--fg-3)", fontSize: 12 }}>Loading scorecard…</div>
                              ) : (
                                <SupplierDetail s={scorecard} />
                              )}
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                  {filteredSuppliers.length === 0 && (
                    <tr><td colSpan={COLUMNS.length} style={{ ...cell, color: "var(--fg-3)" }}>No suppliers match.</td></tr>
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
