import React, { useEffect, useState } from "react";
import { BlobBg } from "../components/layout/BlobBg";
import { PageHero } from "../components/layout/PageHero";
import { Card } from "../components/layout/Card";
import { StatTile } from "../components/StatTile";
import { PrimaryBtn, Pill, SegSelect } from "../components/Buttons";
import { BarChart } from "../charts/BarChart";
import { getCostReductions, getSavingsSummary, getAvoidanceEntries, createAvoidanceEntry } from "../api";
import { fmtUSD, fmtPct, fmtDate } from "../format";
import type { AvoidanceEntry, AvoidanceEntryCreate, CostReductionRow, SavingsSummaryRow } from "../types";

export function CostSavings({ searchQuery = "" }: { searchQuery?: string }) {
  const [reductions, setReductions] = useState<CostReductionRow[]>([]);
  const [avoidance, setAvoidance] = useState<AvoidanceEntry[]>([]);
  const [summary, setSummary] = useState<SavingsSummaryRow[]>([]);
  const [view, setView] = useState<"summary" | "reductions" | "avoidance">("summary");
  const [loading, setLoading] = useState(true);
  const [formOpen, setFormOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [form, setForm] = useState<AvoidanceEntryCreate>({
    fiscal_year: new Date().getFullYear(),
    fiscal_quarter: Math.ceil((new Date().getMonth() + 1) / 3),
    savings_amount_usd: 0,
  });

  useEffect(() => {
    Promise.allSettled([getCostReductions(), getSavingsSummary(), getAvoidanceEntries()])
      .then(([r, s, a]) => {
        if (r.status === "fulfilled") setReductions(r.value);
        if (s.status === "fulfilled") setSummary(s.value);
        if (a.status === "fulfilled") setAvoidance(a.value);
      })
      .finally(() => setLoading(false));
  }, []);

  const totalReduction = summary.reduce((acc, r) => acc + r.reduction_usd, 0);
  const totalAvoidance = summary.reduce((acc, r) => acc + r.avoidance_usd, 0);

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

  async function submitAvoidance() {
    if (form.savings_amount_usd <= 0 || !form.fiscal_year || !form.fiscal_quarter) return;
    setSubmitting(true);
    try {
      const entry = await createAvoidanceEntry(form as AvoidanceEntryCreate);
      setAvoidance((prev) => [entry, ...prev]);
      setFormOpen(false);
      setForm({ fiscal_year: new Date().getFullYear(), fiscal_quarter: Math.ceil((new Date().getMonth() + 1) / 3), savings_amount_usd: 0 });
    } finally {
      setSubmitting(false);
    }
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

        {/* KPI strip */}
        <div style={{ display: "flex", gap: "var(--space-4)", marginBottom: "var(--space-6)", flexWrap: "wrap" }}>
          <StatTile label="Total Reduction" value={fmtUSD(totalReduction, true)} accent="var(--db-green-700)" sub="auto-detected" />
          <StatTile label="Total Avoidance" value={fmtUSD(totalAvoidance, true)} accent="var(--db-yellow-600)" sub="manually logged" />
          <StatTile label="Combined Savings" value={fmtUSD(totalReduction + totalAvoidance, true)} accent="var(--db-lava-600)" />
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
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      {["Segment", "Period", "Reduction", "Avoidance", "Total", "% of Budget"].map((h) => (
                        <th key={h} style={{ padding: "var(--space-3) var(--space-4)", textAlign: "left",
                          fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)",
                          fontWeight: 500, textTransform: "uppercase" }}>
                          {h}
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
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      {["Supplier", "Category", "Period", "Type", "Baseline", "Awarded", "Savings", "Rate"].map((h) => (
                        <th key={h} style={{ padding: "var(--space-3) var(--space-4)", textAlign: "left",
                          fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)",
                          fontWeight: 500, textTransform: "uppercase" }}>
                          {h}
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
                        <td style={{ padding: "var(--space-3) var(--space-4)" }}><Pill>{r.event_type}</Pill></td>
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
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)" }}>
                    {["Supplier", "Category", "Period", "Amount", "Attested By", "Date", "Approved"].map((h) => (
                      <th key={h} style={{ padding: "var(--space-3) var(--space-4)", textAlign: "left",
                        fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)",
                        fontWeight: 500, textTransform: "uppercase" }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredAvoidance.map((a) => (
                    <tr key={a.entry_id} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "var(--space-3) var(--space-4)", fontSize: 13 }}>{a.supplier_name ?? "—"}</td>
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
                        <Pill active={a.approved}>{a.approved ? "✓" : "Pending"}</Pill>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
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
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-3)" }}>
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
                </div>
                <label>
                  <span style={{ fontSize: 12, color: "var(--fg-2)", display: "block", marginBottom: 4 }}>Supplier Name</span>
                  <input style={{ width: "100%" }}
                    value={form.supplier_name ?? ""}
                    onChange={(e) => setForm((f) => ({ ...f, supplier_name: e.target.value }))} />
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
      </div>
    </div>
  );
}
