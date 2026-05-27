import React, { useEffect, useMemo, useState } from "react";
import { BlobBg } from "../components/layout/BlobBg";
import { PageHero } from "../components/layout/PageHero";
import { Card } from "../components/layout/Card";
import { StatTile } from "../components/StatTile";
import { PrimaryBtn, Pill, SegSelect } from "../components/Buttons";
import { MetricTooltip } from "../components/MetricTooltip";
import { HeaderLabel } from "../components/HeaderLabel";
import { METRICS, eventTypeMetric } from "../components/metricDefinitions";
import { BarChart } from "../charts/BarChart";
import {
  getCostReductions,
  getSavingsSummary,
  getAvoidanceEntries,
  createAvoidanceEntry,
  approveAvoidanceEntry,
  rejectAvoidanceEntry,
  getSuppliers,
} from "../api";
import { fmtUSD, fmtPct, fmtDate } from "../format";
import type {
  AvoidanceEntry,
  AvoidanceEntryCreate,
  CostReductionRow,
  SavingsSummaryRow,
  SupplierRow,
} from "../types";

// Helios segment codes — fixed enumeration (matches dim_segment in UC).
const SEGMENT_OPTIONS = [
  { code: "HAD", name: "Helios Aerospace Defense" },
  { code: "HPA", name: "Helios Power & Automation" },
  { code: "HSB", name: "Helios Subsea & Maritime" },
  { code: "HET", name: "Helios Energy Transition" },
  { code: "CORP", name: "Helios Corporate" },
];

export function CostSavings({ searchQuery = "" }: { searchQuery?: string }) {
  const [reductions, setReductions] = useState<CostReductionRow[]>([]);
  const [avoidance, setAvoidance] = useState<AvoidanceEntry[]>([]);
  const [summary, setSummary] = useState<SavingsSummaryRow[]>([]);
  const [suppliers, setSuppliers] = useState<SupplierRow[]>([]);
  const [view, setView] = useState<"summary" | "reductions" | "avoidance">("summary");
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [supplierQuery, setSupplierQuery] = useState("");
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");
  const [actioningId, setActioningId] = useState<string | null>(null);
  const [form, setForm] = useState<AvoidanceEntryCreate>({
    fiscal_year: new Date().getFullYear(),
    fiscal_quarter: Math.ceil((new Date().getMonth() + 1) / 3),
    savings_amount_usd: 0,
  });

  useEffect(() => {
    // Suppliers list is small (<=200) and powers the avoidance form
    // autocomplete; fetch in parallel with the savings data.
    Promise.allSettled([
      getCostReductions(),
      getSavingsSummary(),
      getAvoidanceEntries(),
      getSuppliers({ sort_by: "trailing_12m_spend", exclude_regulated: "false" }),
    ])
      .then(([r, s, a, sup]) => {
        if (r.status === "fulfilled") setReductions(r.value);
        if (s.status === "fulfilled") setSummary(s.value);
        if (a.status === "fulfilled") setAvoidance(a.value);
        if (sup.status === "fulfilled") setSuppliers(sup.value);
      })
      .finally(() => setLoading(false));
  }, []);

  // Approved-only totals (summary already filters approval at the API).
  const totalReduction = summary.reduce((acc, r) => acc + r.reduction_usd, 0);
  const totalAvoidance = summary.reduce((acc, r) => acc + r.avoidance_usd, 0);
  const totalPending = summary.reduce((acc, r) => acc + r.pending_avoidance_usd, 0);

  const q = searchQuery.toLowerCase();
  const filteredReductions = q
    ? reductions.filter(
        (r) =>
          r.supplier_name?.toLowerCase().includes(q) ||
          r.category_primary?.toLowerCase().includes(q) ||
          r.event_title?.toLowerCase().includes(q) ||
          r.event_type?.toLowerCase().includes(q),
      )
    : reductions;
  const filteredAvoidance = q
    ? avoidance.filter(
        (a) =>
          a.supplier_name?.toLowerCase().includes(q) ||
          a.category_primary?.toLowerCase().includes(q) ||
          a.notes?.toLowerCase().includes(q),
      )
    : avoidance;

  const barData = Object.entries(
    reductions.reduce<Record<string, number>>((acc, r) => {
      const k = r.category_primary ?? "Unknown";
      acc[k] = (acc[k] ?? 0) + r.savings_amount_usd;
      return acc;
    }, {}),
  )
    .sort((a, b) => b[1] - a[1])
    .slice(0, 12)
    .map(([label, value]) => ({ label, value }));

  // Supplier autocomplete: simple substring filter on the loaded list,
  // capped at 8 matches so the dropdown stays compact in the modal.
  const supplierMatches = useMemo(() => {
    const qq = supplierQuery.trim().toLowerCase();
    if (!qq) return [];
    return suppliers
      .filter((s) => s.supplier_name?.toLowerCase().includes(qq))
      .slice(0, 8);
  }, [supplierQuery, suppliers]);

  async function submitAvoidance() {
    if (form.savings_amount_usd <= 0 || !form.fiscal_year || !form.fiscal_quarter) return;
    setSubmitting(true);
    try {
      const entry = await createAvoidanceEntry(form as AvoidanceEntryCreate);
      setAvoidance((prev) => [entry, ...prev]);
      // Refresh summary so the Pending sub-line updates immediately.
      try { setSummary(await getSavingsSummary()); } catch { /* best-effort */ }
      setFormOpen(false);
      setSupplierQuery("");
      setForm({
        fiscal_year: new Date().getFullYear(),
        fiscal_quarter: Math.ceil((new Date().getMonth() + 1) / 3),
        savings_amount_usd: 0,
      });
    } finally {
      setSubmitting(false);
    }
  }

  async function approveEntry(id: string) {
    setActioningId(id);
    try {
      const updated = await approveAvoidanceEntry(id);
      setAvoidance((prev) => prev.map((e) => (e.entry_id === id ? updated : e)));
      try { setSummary(await getSavingsSummary()); } catch { /* best-effort */ }
    } finally {
      setActioningId(null);
    }
  }

  async function confirmReject() {
    if (!rejectingId || !rejectReason.trim()) return;
    setActioningId(rejectingId);
    try {
      const updated = await rejectAvoidanceEntry(rejectingId, rejectReason.trim());
      setAvoidance((prev) => prev.map((e) => (e.entry_id === rejectingId ? updated : e)));
      try { setSummary(await getSavingsSummary()); } catch { /* best-effort */ }
      setRejectingId(null);
      setRejectReason("");
    } finally {
      setActioningId(null);
    }
  }

  // Approval state label + tone derived once per row.
  function approvalState(a: AvoidanceEntry): { label: string; tone: "success" | "warning" | "danger" } {
    if (a.approved) return { label: "✓ Approved", tone: "success" };
    if (a.rejected_at) return { label: "✗ Rejected", tone: "danger" };
    return { label: "Pending", tone: "warning" };
  }

  return (
    <div style={{ position: "relative", flex: 1, overflow: "auto", padding: "var(--space-6)" }}>
      <BlobBg />
      <div style={{ position: "relative", zIndex: 1, maxWidth: 1200 }}>
        <PageHero
          eyebrow="Plan"
          title="Cost Savings"
          subtitle="Auto-detected reductions from sourcing events + manually logged avoidance entries."
          right={
            <div style={{ display: "flex", gap: "var(--space-3)" }}>
              <SegSelect
                options={[
                  { label: "Summary", value: "summary" },
                  { label: "Reductions", value: "reductions" },
                  { label: "Avoidance", value: "avoidance" },
                ]}
                value={view}
                onChange={(v) => setView(v as typeof view)}
              />
              {view === "avoidance" && (
                <PrimaryBtn onClick={() => setFormOpen(true)}>+ Log Avoidance</PrimaryBtn>
              )}
            </div>
          }
        />

        {/* KPI strip — approved totals only; pending shown as separate sub-line */}
        <div style={{ display: "flex", gap: "var(--space-4)", marginBottom: "var(--space-6)", flexWrap: "wrap" }}>
          <StatTile label="Total Reduction" value={fmtUSD(totalReduction, true)}
            accent="var(--db-green-700)" sub="auto-detected"
            tooltip={METRICS.totalReduction} />
          <StatTile label="Total Avoidance" value={fmtUSD(totalAvoidance, true)}
            accent="var(--db-yellow-600)"
            sub={totalPending > 0
              ? `approved · pending ${fmtUSD(totalPending, true)}`
              : "manually logged, approved only"}
            tooltip={METRICS.totalAvoidance} />
          <StatTile label="Combined Savings" value={fmtUSD(totalReduction + totalAvoidance, true)}
            accent="var(--db-lava-600)" sub="reductions + approved avoidance"
            tooltip={METRICS.combinedSavings} />
        </div>

        {/* Summary view */}
        {view === "summary" && !loading && (
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)" }}>
            <Card>
              <h3 style={{ fontSize: "var(--fs-body)", fontWeight: 700, marginBottom: "var(--space-4)" }}>
                Savings by Category
              </h3>
              <BarChart
                data={barData}
                color="var(--db-lava-600)"
                formatValue={(v) => fmtUSD(v, true)}
                height={Math.max(280, barData.length * 28)}
              />
            </Card>
            <Card padding="0">
              <div style={{ padding: "var(--space-4)", borderBottom: "1px solid var(--border)" }}>
                <h3 style={{ fontSize: "var(--fs-body)", fontWeight: 700 }}>Savings vs Budget by Segment × Quarter</h3>
              </div>
              <div style={{ overflowX: "auto" }}>
                <table style={{ minWidth: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      {[
                        { label: "Segment" },
                        { label: "Period" },
                        { label: "Reduction", tooltip: METRICS.totalReduction },
                        { label: "Avoidance", tooltip: METRICS.totalAvoidance },
                        { label: "Pending", tooltip: METRICS.pendingAvoidance },
                        { label: "Total", tooltip: METRICS.combinedSavings },
                        { label: "% of Budget", tooltip: METRICS.savingsPctOfBudget },
                      ].map((h) => (
                        <th key={h.label} style={{ padding: "var(--space-3) var(--space-4)", textAlign: "left",
                          fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)",
                          fontWeight: 500, textTransform: "uppercase" }}>
                          <HeaderLabel label={h.label} tooltip={h.tooltip} />
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {summary.slice(0, 30).map((r) => (
                      <tr key={`${r.segment_code}-${r.fiscal_year}-${r.fiscal_quarter}`}
                        style={{ borderBottom: "1px solid var(--border)" }}>
                        <td style={{ padding: "var(--space-2) var(--space-4)", fontSize: 12 }}>{r.segment_code ?? "—"}</td>
                        <td style={{ padding: "var(--space-2) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
                          FY{String(r.fiscal_year).slice(-2)} Q{r.fiscal_quarter}
                        </td>
                        <td style={{ padding: "var(--space-2) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12,
                          color: "var(--success)" }}>
                          {fmtUSD(r.reduction_usd, true)}
                        </td>
                        <td style={{ padding: "var(--space-2) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12,
                          color: "var(--warning)" }}>
                          {fmtUSD(r.avoidance_usd, true)}
                        </td>
                        <td style={{ padding: "var(--space-2) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12,
                          color: "var(--fg-3)" }}
                          title="Pending avoidance — not yet counted in Total">
                          {r.pending_avoidance_usd > 0 ? fmtUSD(r.pending_avoidance_usd, true) : "—"}
                        </td>
                        <td style={{ padding: "var(--space-2) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12,
                          fontWeight: 600 }}>
                          {fmtUSD(r.total_savings_usd, true)}
                        </td>
                        <td style={{ padding: "var(--space-2) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                          {fmtPct(r.savings_pct_of_budget)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
        )}

        {/* Reductions table */}
        {view === "reductions" && (
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
                        { label: "Period" },
                        { label: "Type" },
                        { label: "Baseline", tooltip: METRICS.savingsBaseline },
                        { label: "Awarded", tooltip: METRICS.savingsAwarded },
                        { label: "Savings", tooltip: METRICS.totalReduction },
                        { label: "Rate", tooltip: METRICS.savingsRate },
                      ].map((h) => (
                        <th key={h.label} style={{ padding: "var(--space-3) var(--space-4)", textAlign: "left",
                          fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)",
                          fontWeight: 500, textTransform: "uppercase" }}>
                          <HeaderLabel label={h.label} tooltip={h.tooltip} />
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {filteredReductions.slice(0, 200).map((r) => (
                      <tr key={r.savings_event_id} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontSize: 13 }}>{r.supplier_name ?? r.supplier_id ?? "—"}</td>
                        <td style={{ padding: "var(--space-3) var(--space-4)" }}><Pill>{r.category_primary ?? "—"}</Pill></td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
                          FY{String(r.fiscal_year).slice(-2)} Q{r.fiscal_quarter}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)" }}>
                          {/* Event type pill — back-calculated baseline rate explained on hover. */}
                          <MetricTooltip content={eventTypeMetric(r.event_type)} hoverOnly>
                            <Pill>{r.event_type}</Pill>
                          </MetricTooltip>
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                          {fmtUSD(r.baseline_amount, true)}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                          {fmtUSD(r.awarded_amount, true)}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12,
                          color: "var(--success)", fontWeight: 600 }}>
                          {fmtUSD(r.savings_amount_usd, true)}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                          {fmtPct(r.savings_rate * 100)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        )}

        {/* Avoidance table */}
        {view === "avoidance" && (
          <Card padding="0">
            {loading ? (
              <div style={{ padding: "var(--space-7)", textAlign: "center", color: "var(--fg-3)" }}>Loading…</div>
            ) : avoidance.length === 0 ? (
              <div style={{ padding: "var(--space-7)", textAlign: "center", color: "var(--fg-3)" }}>
                No avoidance entries yet. Click "+ Log Avoidance" to add one.
              </div>
            ) : (
              <div style={{ overflowX: "auto" }}>
              <table style={{ minWidth: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)" }}>
                    {[
                      { label: "Supplier" },
                      { label: "Segment" },
                      { label: "Category" },
                      { label: "Period" },
                      { label: "Amount", tooltip: METRICS.totalAvoidance },
                      { label: "Attested By" },
                      { label: "Date" },
                      { label: "Status", tooltip: METRICS.pendingPill },
                      { label: "Actions" },
                    ].map((h) => (
                      <th key={h.label} style={{ padding: "var(--space-3) var(--space-4)", textAlign: "left",
                        fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)",
                        fontWeight: 500, textTransform: "uppercase" }}>
                        <HeaderLabel label={h.label} tooltip={h.tooltip} />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredAvoidance.map((a) => {
                    const state = approvalState(a);
                    const busy = actioningId === a.entry_id;
                    return (
                      <tr key={a.entry_id} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontSize: 13 }}>{a.supplier_name ?? "—"}</td>
                        <td style={{ padding: "var(--space-3) var(--space-4)" }}>
                          {a.segment_code ? <Pill>{a.segment_code}</Pill> : "—"}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)" }}><Pill>{a.category_primary ?? "—"}</Pill></td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
                          FY{String(a.fiscal_year).slice(-2)} Q{a.fiscal_quarter}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12,
                          color: "var(--warning)", fontWeight: 600 }}>
                          {fmtUSD(a.savings_amount_usd, true)}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontSize: 12, color: "var(--fg-2)" }}>{a.attested_by}</td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
                          {fmtDate(a.attested_at)}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)" }}>
                          <MetricTooltip
                            content={
                              state.tone === "success" ? METRICS.approvedPill :
                              state.tone === "danger"  ? METRICS.rejectedPill :
                              METRICS.pendingPill
                            }
                            placement="bottom-right"
                            hoverOnly
                          >
                            <span
                              title={a.rejection_reason ? `Rejected: ${a.rejection_reason}` : undefined}
                              style={{
                                fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 600,
                                color:
                                  state.tone === "success" ? "var(--success)" :
                                  state.tone === "danger"  ? "var(--danger)"  :
                                  "var(--warning)",
                                cursor: "help",
                              }}
                            >
                              {state.label}
                            </span>
                          </MetricTooltip>
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)" }}>
                          {a.approved ? (
                            <span style={{ fontSize: 11, color: "var(--fg-3)" }}>—</span>
                          ) : (
                            <div style={{ display: "flex", gap: "var(--space-1)" }}>
                              <button
                                onClick={() => approveEntry(a.entry_id)}
                                disabled={busy}
                                style={{
                                  padding: "2px 8px", fontSize: 11, fontFamily: "var(--font-mono)",
                                  background: "transparent", border: "1px solid var(--success)",
                                  color: "var(--success)", borderRadius: "var(--radius-sm)",
                                  cursor: busy ? "not-allowed" : "pointer",
                                }}
                              >
                                Approve
                              </button>
                              <button
                                onClick={() => { setRejectingId(a.entry_id); setRejectReason(""); }}
                                disabled={busy}
                                style={{
                                  padding: "2px 8px", fontSize: 11, fontFamily: "var(--font-mono)",
                                  background: "transparent", border: "1px solid var(--danger)",
                                  color: "var(--danger)", borderRadius: "var(--radius-sm)",
                                  cursor: busy ? "not-allowed" : "pointer",
                                }}
                              >
                                Reject
                              </button>
                            </div>
                          )}
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

        {/* Manual avoidance form */}
        {formOpen && (
          <div style={{ position: "fixed", inset: 0, background: "rgba(11,32,38,0.5)", zIndex: 100,
            display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Card style={{ width: 480, position: "relative" }} accent="var(--db-yellow-600)">
              <h3 style={{ fontSize: "var(--fs-h4)", marginBottom: "var(--space-4)" }}>Log Cost Avoidance</h3>
              <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-3)" }}>
                <label>
                  <span style={{ fontSize: 12, color: "var(--fg-2)", display: "block", marginBottom: 4 }}>Savings Amount (USD) *</span>
                  <input type="number" style={{ width: "100%" }}
                    value={form.savings_amount_usd ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, savings_amount_usd: parseFloat(e.target.value) || 0 }))} />
                </label>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "var(--space-3)" }}>
                  <label>
                    <span style={{ fontSize: 12, color: "var(--fg-2)", display: "block", marginBottom: 4 }}>Fiscal Year *</span>
                    <input type="number" style={{ width: "100%" }}
                      value={form.fiscal_year}
                      onChange={(e) => setForm((f) => ({ ...f, fiscal_year: parseInt(e.target.value) }))} />
                  </label>
                  <label>
                    <span style={{ fontSize: 12, color: "var(--fg-2)", display: "block", marginBottom: 4 }}>Quarter *</span>
                    <select style={{ width: "100%" }}
                      value={form.fiscal_quarter}
                      onChange={(e) => setForm((f) => ({ ...f, fiscal_quarter: parseInt(e.target.value) }))}>
                      {[1, 2, 3, 4].map((q) => <option key={q} value={q}>Q{q}</option>)}
                    </select>
                  </label>
                  <label>
                    <span style={{ fontSize: 12, color: "var(--fg-2)", display: "block", marginBottom: 4 }}>Segment</span>
                    <select style={{ width: "100%" }}
                      value={form.segment_code ?? ""}
                      onChange={(e) => setForm((f) => ({ ...f, segment_code: e.target.value || null }))}>
                      <option value="">—</option>
                      {SEGMENT_OPTIONS.map((s) => (
                        <option key={s.code} value={s.code}>{s.code}</option>
                      ))}
                    </select>
                  </label>
                </div>
                <label style={{ position: "relative" }}>
                  <span style={{ fontSize: 12, color: "var(--fg-2)", display: "block", marginBottom: 4 }}>Supplier</span>
                  <input
                    style={{ width: "100%" }}
                    placeholder="Type to search…"
                    value={supplierQuery || form.supplier_name || ""}
                    onChange={(e) => {
                      setSupplierQuery(e.target.value);
                      // Free-form text — clear linkage until user picks a match.
                      setForm((f) => ({ ...f, supplier_name: e.target.value, supplier_id: null }));
                    }}
                  />
                  {supplierMatches.length > 0 && supplierQuery && (
                    <div style={{ position: "absolute", top: "100%", left: 0, right: 0, zIndex: 10,
                      background: "var(--bg)", border: "1px solid var(--border)",
                      borderRadius: "var(--radius-sm)", maxHeight: 200, overflowY: "auto",
                      boxShadow: "var(--shadow-2)" }}>
                      {supplierMatches.map((s) => (
                        <div
                          key={s.supplier_id}
                          onClick={() => {
                            setForm((f) => ({
                              ...f,
                              supplier_id: s.supplier_id,
                              supplier_name: s.supplier_name,
                              // Default category to supplier's primary when picking from match.
                              category_primary: f.category_primary || s.category_primary,
                            }));
                            setSupplierQuery("");
                          }}
                          style={{ padding: "var(--space-2) var(--space-3)", cursor: "pointer", fontSize: 12,
                            borderBottom: "1px solid var(--border)" }}
                        >
                          <div style={{ color: "var(--fg-1)" }}>{s.supplier_name ?? s.supplier_id}</div>
                          <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)" }}>
                            {s.category_primary ?? "—"} · {s.region ?? "—"}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </label>
                <label>
                  <span style={{ fontSize: 12, color: "var(--fg-2)", display: "block", marginBottom: 4 }}>Category</span>
                  <input style={{ width: "100%" }}
                    value={form.category_primary ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, category_primary: e.target.value }))} />
                </label>
                <label>
                  <span style={{ fontSize: 12, color: "var(--fg-2)", display: "block", marginBottom: 4 }}>Baseline Context</span>
                  <textarea rows={2} style={{ width: "100%", resize: "vertical" }}
                    placeholder="e.g. Supplier requested +20%, negotiated to +5%"
                    value={form.baseline_context ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, baseline_context: e.target.value }))} />
                </label>
                <div style={{ fontSize: 11, color: "var(--fg-3)", marginTop: 0 }}>
                  Submitted with attestation; entries are pending until a reviewer approves them.
                </div>
                <div style={{ display: "flex", gap: "var(--space-3)", justifyContent: "flex-end", marginTop: "var(--space-2)" }}>
                  <button onClick={() => setFormOpen(false)}
                    style={{ fontSize: 14, color: "var(--fg-2)", background: "none", border: "none", cursor: "pointer" }}>
                    Cancel
                  </button>
                  <PrimaryBtn onClick={submitAvoidance} disabled={submitting}>
                    {submitting ? "Submitting…" : "Submit with Attestation"}
                  </PrimaryBtn>
                </div>
              </div>
            </Card>
          </div>
        )}

        {/* Reject reason prompt */}
        {rejectingId && (
          <div style={{ position: "fixed", inset: 0, background: "rgba(11,32,38,0.5)", zIndex: 100,
            display: "flex", alignItems: "center", justifyContent: "center" }}>
            <Card style={{ width: 420, position: "relative" }} accent="var(--danger)">
              <h3 style={{ fontSize: "var(--fs-h4)", marginBottom: "var(--space-3)" }}>Reject Avoidance Entry</h3>
              <div style={{ fontSize: 12, color: "var(--fg-2)", marginBottom: "var(--space-3)" }}>
                A reason is required and will be visible on the entry.
              </div>
              <textarea
                rows={3}
                style={{ width: "100%", resize: "vertical" }}
                placeholder="e.g. baseline not auditable — no supplier quote attached"
                value={rejectReason}
                onChange={(e) => setRejectReason(e.target.value)}
                autoFocus
              />
              <div style={{ display: "flex", gap: "var(--space-3)", justifyContent: "flex-end", marginTop: "var(--space-3)" }}>
                <button
                  onClick={() => { setRejectingId(null); setRejectReason(""); }}
                  style={{ fontSize: 14, color: "var(--fg-2)", background: "none", border: "none", cursor: "pointer" }}
                >
                  Cancel
                </button>
                <PrimaryBtn
                  onClick={confirmReject}
                  disabled={!rejectReason.trim() || actioningId === rejectingId}
                  style={{ background: "var(--danger)" }}
                >
                  {actioningId === rejectingId ? "Rejecting…" : "Confirm Reject"}
                </PrimaryBtn>
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}
