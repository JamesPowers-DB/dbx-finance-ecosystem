import React, { useEffect, useMemo, useState } from "react";
import { BlobBg } from "../components/layout/BlobBg";
import { PageHero } from "../components/layout/PageHero";
import { Card } from "../components/layout/Card";
import { Pill, SegSelect } from "../components/Buttons";
import { MetricTooltip, type MetricTooltipContent } from "../components/MetricTooltip";
import { HeaderLabel } from "../components/HeaderLabel";
import { METRICS } from "../components/metricDefinitions";
import { BarChart } from "../charts/BarChart";
import { SparklineChart } from "../charts/SparklineChart";
import { getSuppliers, getRenegotiationTargets, getSupplierScorecard } from "../api";
import { fmtUSD, fmtPct, fmtInt, fmtDate, fmtDays } from "../format";
import type { RenegotiationTarget, SupplierRow, SupplierScorecard } from "../types";

type DetailTab = "summary" | "contracts" | "trend";

export function Suppliers({ searchQuery = "" }: { searchQuery?: string }) {
  const [suppliers, setSuppliers] = useState<SupplierRow[]>([]);
  const [targets, setTargets] = useState<RenegotiationTarget[]>([]);
  const [view, setView] = useState<"scorecard" | "targets">("scorecard");
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [scorecard, setScorecard] = useState<SupplierScorecard | null>(null);
  const [scoreLoading, setScoreLoading] = useState(false);
  const [tab, setTab] = useState<DetailTab>("summary");

  useEffect(() => {
    Promise.all([
      getSuppliers({ sort_by: "trailing_12m_spend", exclude_regulated: "true" }),
      getRenegotiationTargets(),
    ])
      .then(([s, t]) => { setSuppliers(s); setTargets(t); })
      .finally(() => setLoading(false));
  }, []);

  // Mirror the Contracts drilldown pattern: row click opens an inline panel
  // that lazy-loads the scorecard endpoint.
  useEffect(() => {
    if (!selectedId) {
      setScorecard(null);
      setTab("summary");
      return;
    }
    setScoreLoading(true);
    setScorecard(null);
    setTab("summary");
    getSupplierScorecard(selectedId)
      .then(setScorecard)
      .catch(() => setScorecard(null))
      .finally(() => setScoreLoading(false));
  }, [selectedId]);

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

  const selectedRow = useMemo(
    () => suppliers.find((s) => s.supplier_id === selectedId) ?? null,
    [suppliers, selectedId],
  );

  // Open panel only on Scorecard view (Targets view has its own row semantic).
  const showPanel = view === "scorecard" && selectedId;

  return (
    <div style={{ position: "relative", flex: 1, overflow: "auto", padding: "var(--space-6)" }}>
      <BlobBg />
      <div style={{ position: "relative", zIndex: 1, maxWidth: 1200 }}>
        <PageHero
          eyebrow="Review"
          title="Supplier Performance"
          subtitle="Trailing 12-month paid-spend scorecard and payment-terms renegotiation targets. Regulated suppliers excluded from targets."
          right={
            <SegSelect
              options={[
                { label: "Scorecard", value: "scorecard" },
                { label: "Renegotiation Targets", value: "targets" },
              ]}
              value={view}
              onChange={(v) => {
                setView(v as "scorecard" | "targets");
                setSelectedId(null);
              }}
            />
          }
        />

        <div style={{ display: "grid", gridTemplateColumns: showPanel ? "1fr 400px" : "1fr",
          gap: "var(--space-5)" }}>
          {view === "scorecard" && (
            <Card padding="0">
              {loading ? (
                <div style={{ padding: "var(--space-7)", textAlign: "center", color: "var(--fg-3)" }}>Loading…</div>
              ) : (
                <div style={{ overflowX: "auto" }}>
                  <table style={{ minWidth: "100%", borderCollapse: "collapse" }}>
                    <thead>
                      <tr style={{ borderBottom: "1px solid var(--border)" }}>
                        {[
                          { label: "Supplier" },
                          { label: "Category" },
                          { label: "Region" },
                          { label: "T12M Spend", tooltip: METRICS.t12mSupplierSpend },
                          { label: "Invoices", tooltip: METRICS.invoiceCount },
                          { label: "On-Time Payment %", tooltip: METRICS.onTimePayment },
                          { label: "Avg DPO", tooltip: METRICS.avgDpo },
                          { label: "Terms", tooltip: METRICS.paymentTerms },
                          { label: "Maverick", tooltip: METRICS.measuredMaverick },
                        ].map((h) => (
                          <th key={h.label} style={{ padding: "var(--space-3) var(--space-4)", textAlign: "left",
                            fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)",
                            fontWeight: 500, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                            <HeaderLabel label={h.label} tooltip={h.tooltip} />
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {filteredSuppliers.map((s) => {
                        // Threshold matches list-view convention: >15% maverick
                        // share is the renegotiation flag.
                        const isMaverick = (s.measured_maverick_pct ?? 0) > 15.0;
                        // Maverick strip dot position — scale [0, 30%] across the strip
                        // so visual differentiation is meaningful for low single-digit
                        // values that dominate good suppliers.
                        const dotPct = Math.min((s.measured_maverick_pct ?? 0) / 30.0, 1) * 100;
                        return (
                          <tr
                            key={s.supplier_id}
                            onClick={() => setSelectedId(selectedId === s.supplier_id ? null : s.supplier_id)}
                            style={{
                              borderBottom: "1px solid var(--border)",
                              background: selectedId === s.supplier_id ? "var(--bg-subtle)" : "transparent",
                              cursor: "pointer",
                            }}
                          >
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
                              {/* Maverick strip — observed (not synthetic). MetricTooltip
                                  replaces the prior native title attribute so the hover
                                  carries the same Period / Definition / Formula explainer. */}
                              <MetricTooltip
                                content={{
                                  ...METRICS.measuredMaverick,
                                  metric: `${METRICS.measuredMaverick.metric} — ${fmtPct(s.measured_maverick_pct)}`,
                                }}
                                placement="bottom-right"
                                hoverOnly
                              >
                                <div style={{ position: "relative", width: 80, height: 12, cursor: "help" }}>
                                  <div style={{ position: "absolute", top: 5, left: 0, right: 0, height: 2,
                                    background: "var(--border)", borderRadius: 1 }} />
                                  <div style={{
                                    position: "absolute",
                                    top: 2,
                                    left: `${dotPct}%`,
                                    width: 8, height: 8, borderRadius: "50%",
                                    background: isMaverick ? "var(--danger)" : "var(--db-navy-800)",
                                    transform: "translateX(-50%)",
                                  }} />
                                </div>
                              </MetricTooltip>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          )}

          {/* Drilldown panel — Scorecard view only */}
          {showPanel && (
            <Card accent="var(--db-navy-800)">
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start",
                marginBottom: "var(--space-3)" }}>
                <div>
                  <h3 style={{ fontSize: "var(--fs-body)", fontWeight: 700 }}>
                    {scorecard?.supplier_name ?? selectedRow?.supplier_name ?? selectedId}
                  </h3>
                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)",
                    marginTop: 2 }}>
                    {(scorecard?.region ?? selectedRow?.region ?? "—")} · {scorecard?.category_primary ?? selectedRow?.category_primary ?? "—"}
                  </div>
                </div>
                <button
                  onClick={() => setSelectedId(null)}
                  aria-label="Close panel"
                  style={{ background: "none", border: "none", cursor: "pointer",
                    color: "var(--fg-3)", fontSize: 18, lineHeight: 1, padding: 0 }}
                >
                  ×
                </button>
              </div>

              {scoreLoading || !scorecard ? (
                <div style={{ padding: "var(--space-5) 0", textAlign: "center", color: "var(--fg-3)", fontSize: 12 }}>
                  Loading scorecard…
                </div>
              ) : (
                <>
                  {/* KPI strip — T12M paid, consistent denominator across all four */}
                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-2)",
                    marginBottom: "var(--space-3)" }}>
                    <PanelStat label="T12M Spend" value={fmtUSD(scorecard.trailing_12m_spend, true)}
                      tooltip={METRICS.t12mSupplierSpend} />
                    <PanelStat label="Invoices" value={fmtInt(scorecard.invoice_count)}
                      tooltip={METRICS.invoiceCount} />
                    <PanelStat label="On-Time Payment %"
                      value={fmtPct(scorecard.on_time_payment_pct)}
                      tone={(scorecard.on_time_payment_pct ?? 0) < 80 ? "danger" : "success"}
                      tooltip={METRICS.onTimePayment} />
                    <PanelStat label="Avg DPO"
                      value={scorecard.avg_dpo != null ? `${Number(scorecard.avg_dpo).toFixed(1)}d` : "—"}
                      tooltip={METRICS.avgDpo} />
                    <PanelStat label="Maverick %"
                      value={fmtPct(scorecard.measured_maverick_pct)}
                      tone={(scorecard.measured_maverick_pct ?? 0) > 15.0 ? "danger" : "default"}
                      tooltip={METRICS.measuredMaverick} />
                    <PanelStat label="Terms" value={scorecard.payment_terms ?? "—"}
                      tooltip={METRICS.paymentTerms} />
                  </div>

                  <div style={{ marginBottom: "var(--space-3)" }}>
                    <SegSelect
                      options={[
                        { label: "Summary", value: "summary" },
                        { label: "Contracts", value: "contracts" },
                        { label: "Trend", value: "trend" },
                      ]}
                      value={tab}
                      onChange={(v) => setTab(v as DetailTab)}
                    />
                  </div>

                  {tab === "summary" && (
                    scorecard.category_breakdown.length === 0 ? (
                      <div style={{ padding: "var(--space-5) 0", textAlign: "center", color: "var(--fg-3)", fontSize: 12 }}>
                        No T12M paid spend.
                      </div>
                    ) : (
                      <div>
                        <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)",
                          textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "var(--space-2)" }}>
                          Spend by Category (T12M)
                        </div>
                        <BarChart
                          data={scorecard.category_breakdown.slice(0, 8).map((c) => ({
                            label: c.category ?? "Unknown",
                            value: c.spend_usd,
                          }))}
                          color="var(--db-lava-600)"
                          formatValue={(v) => fmtUSD(v, true)}
                          width={360}
                          height={Math.max(160, Math.min(scorecard.category_breakdown.length, 8) * 28)}
                        />
                      </div>
                    )
                  )}

                  {tab === "contracts" && (
                    scorecard.contracts.length === 0 ? (
                      <div style={{ padding: "var(--space-5) 0", textAlign: "center", color: "var(--fg-3)", fontSize: 12 }}>
                        No currently active contracts.
                      </div>
                    ) : (
                      <div style={{ maxHeight: 260, overflowY: "auto" }}>
                        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                          <thead>
                            <tr style={{ borderBottom: "1px solid var(--border)" }}>
                              {["Title", "Type", "Committed", "Used", "Expires"].map((h) => (
                                <th key={h} style={{ padding: "var(--space-2)", textAlign: "left",
                                  fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)",
                                  fontWeight: 500, textTransform: "uppercase", letterSpacing: "0.06em",
                                  position: "sticky", top: 0, background: "var(--bg)" }}>
                                  {h}
                                </th>
                              ))}
                            </tr>
                          </thead>
                          <tbody>
                            {scorecard.contracts.map((c) => (
                              <tr key={c.contract_workspace_id} style={{ borderBottom: "1px solid var(--border)" }}>
                                <td style={{ padding: "var(--space-2)", fontSize: 11, maxWidth: 140,
                                  overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                  {c.title}
                                </td>
                                <td style={{ padding: "var(--space-2)" }}>
                                  <Pill>{c.contract_type}</Pill>
                                </td>
                                <td style={{ padding: "var(--space-2)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
                                  {fmtUSD(c.total_committed_spend, true)}
                                </td>
                                <td style={{ padding: "var(--space-2)", fontFamily: "var(--font-mono)", fontSize: 11,
                                  color: (c.pct_consumed ?? 0) > 90 ? "var(--danger)" : "var(--fg-1)" }}>
                                  {fmtPct(c.pct_consumed)}
                                </td>
                                <td style={{ padding: "var(--space-2)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
                                  {fmtDate(c.expiration_date)}{c.days_to_expiration != null
                                    ? ` (${fmtDays(c.days_to_expiration)})` : ""}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )
                  )}

                  {tab === "trend" && (
                    scorecard.spend_trend.length < 2 ? (
                      <div style={{ padding: "var(--space-5) 0", textAlign: "center", color: "var(--fg-3)", fontSize: 12 }}>
                        Not enough quarterly data for a trend.
                      </div>
                    ) : (
                      <div>
                        <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)",
                          textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "var(--space-2)" }}>
                          Paid spend by quarter (last 8)
                        </div>
                        <SparklineChart
                          values={scorecard.spend_trend.map((q) => q.spend_usd)}
                          width={360}
                          height={120}
                          showDots
                        />
                        <div style={{ display: "flex", justifyContent: "space-between",
                          fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)",
                          marginTop: "var(--space-1)" }}>
                          <span>FY{String(scorecard.spend_trend[0].fiscal_year).slice(-2)} Q{scorecard.spend_trend[0].fiscal_quarter}</span>
                          <span>FY{String(scorecard.spend_trend[scorecard.spend_trend.length - 1].fiscal_year).slice(-2)} Q{scorecard.spend_trend[scorecard.spend_trend.length - 1].fiscal_quarter}</span>
                        </div>
                      </div>
                    )
                  )}
                </>
              )}
            </Card>
          )}
        </div>

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
                <table style={{ minWidth: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      {[
                        { label: "Supplier" },
                        { label: "Category" },
                        { label: "T12M Spend", tooltip: METRICS.t12mSupplierSpend },
                        { label: "Current Terms", tooltip: METRICS.paymentTerms },
                        { label: "Current DPO", tooltip: METRICS.avgDpo },
                        { label: "Target DPO", tooltip: METRICS.workingCapitalOpp },
                        { label: "WC Opportunity", tooltip: METRICS.workingCapitalOpp },
                      ].map((h) => (
                        <th key={h.label} style={{ padding: "var(--space-3) var(--space-4)", textAlign: "left",
                          fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)",
                          fontWeight: 500, letterSpacing: "0.06em", textTransform: "uppercase" }}>
                          <HeaderLabel label={h.label} tooltip={h.tooltip} />
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

// Compact KPI cell used inside the drilldown panel. Mirrors StatTile typography
// but smaller, since the panel is 400px wide and needs 2x3 dense layout.
function PanelStat({
  label,
  value,
  tone = "default",
  tooltip,
}: {
  label: string;
  value: string;
  tone?: "default" | "success" | "danger";
  tooltip?: MetricTooltipContent;
}) {
  const color =
    tone === "success" ? "var(--success)" :
    tone === "danger" ? "var(--danger)" :
    "var(--fg-1)";
  return (
    <div style={{ padding: "var(--space-2) var(--space-3)", background: "var(--bg-subtle)",
      borderRadius: "var(--radius-sm)" }}>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--fg-3)",
        textTransform: "uppercase", letterSpacing: "0.06em",
        display: "inline-flex", alignItems: "center", gap: 4 }}>
        {label}
        {tooltip && <MetricTooltip content={tooltip} iconSize={10} />}
      </div>
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, color, fontWeight: 600,
        marginTop: 2 }}>
        {value}
      </div>
    </div>
  );
}
