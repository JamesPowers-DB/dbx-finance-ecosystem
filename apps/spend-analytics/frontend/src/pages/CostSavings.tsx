import React, { useEffect, useMemo, useState } from "react";
import { BlobBg } from "../components/layout/BlobBg";
import { PageHero } from "../components/layout/PageHero";
import { Card } from "../components/layout/Card";
import { StatTile } from "../components/StatTile";
import { PrimaryBtn, SecondaryBtn, Pill } from "../components/Buttons";
import { BarChart } from "../charts/BarChart";
import { SAVINGS_TYPES, SAVINGS_TYPE_LABEL, CLASS_LABEL } from "../components/savingsTaxonomy";
import {
  getSavingsRegister,
  getSavingsKpis,
  searchSavingsArtifacts,
  submitSavings,
  attestSavings,
  rejectSavings,
  getMe,
} from "../api";
import { fmtUSD, fmtPct, fmtInt, fmtDate } from "../format";
import type { SavingsRecord, SavingsKpis, SavingsArtifact, SavingsClass, SavingsStatus } from "../types";

const fyq = (fy: number, fq: number) => `FY${String(fy).slice(2)} Q${fq}`;
const num = (v: unknown): number => { const n = Number(v); return Number.isFinite(n) ? n : 0; };

const STATUS_TONE: Record<SavingsStatus, { color: string; label: string }> = {
  pending:  { color: "var(--warning)", label: "Pending" },
  attested: { color: "var(--db-green-700)", label: "Attested" },
  rejected: { color: "var(--danger)", label: "Rejected" },
};

const cell: React.CSSProperties = { padding: "var(--space-3) var(--space-4)" };
const th: React.CSSProperties = { ...cell, textAlign: "left", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", fontWeight: 500, letterSpacing: "0.06em", textTransform: "uppercase" };
const detailLabel: React.CSSProperties = { fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.05em" };

function StatusChip({ status }: { status: SavingsStatus }) {
  const t = STATUS_TONE[status];
  return (
    <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 600, color: t.color, border: `1px solid ${t.color}`, borderRadius: "var(--radius-pill)", padding: "2px 9px", whiteSpace: "nowrap" }}>
      {t.label}
    </span>
  );
}

export function CostSavings({ searchQuery = "" }: { searchQuery?: string }) {
  const [records, setRecords] = useState<SavingsRecord[]>([]);
  const [kpis, setKpis] = useState<SavingsKpis | null>(null);
  const [loading, setLoading] = useState(true);
  const [me, setMe] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<SavingsStatus | "">("");
  const [classFilter, setClassFilter] = useState<SavingsClass | "">("");
  const [selected, setSelected] = useState<string | null>(null);
  const [actioning, setActioning] = useState<string | null>(null);
  const [rejectingId, setRejectingId] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  // Log-savings form
  const [formOpen, setFormOpen] = useState(false);
  const [artifactQuery, setArtifactQuery] = useState("");
  const [artifactResults, setArtifactResults] = useState<SavingsArtifact[]>([]);
  const [artifact, setArtifact] = useState<SavingsArtifact | null>(null);
  const [savingsType, setSavingsType] = useState<string>("");
  const [savingsAmount, setSavingsAmount] = useState<string>("");
  const [baselineContext, setBaselineContext] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => { getMe().then((u) => setMe(u.email)).catch(() => {}); }, []);

  const reload = () => {
    setLoading(true);
    Promise.all([
      getSavingsRegister({ status: statusFilter || undefined, savings_class: classFilter || undefined }),
      getSavingsKpis(),
    ])
      .then(([r, k]) => { setRecords(r); setKpis(k); })
      .catch(() => { setRecords([]); setKpis(null); })
      .finally(() => setLoading(false));
  };
  useEffect(reload, [statusFilter, classFilter]);

  // Artifact search for the Log form
  useEffect(() => {
    if (!formOpen || artifactQuery.trim().length < 2) { setArtifactResults([]); return; }
    let live = true;
    searchSavingsArtifacts(artifactQuery.trim())
      .then((r) => { if (live) setArtifactResults(r); })
      .catch(() => { if (live) setArtifactResults([]); });
    return () => { live = false; };
  }, [artifactQuery, formOpen]);

  const q = searchQuery.toLowerCase();
  const rows = useMemo(
    () => (q ? records.filter((r) =>
      r.supplier_name?.toLowerCase().includes(q) ||
      r.artifact_title?.toLowerCase().includes(q) ||
      r.artifact_id.toLowerCase().includes(q) ||
      SAVINGS_TYPE_LABEL[r.savings_type]?.toLowerCase().includes(q),
    ) : records),
    [records, q],
  );

  const quarterBars = useMemo(
    () => (kpis?.by_quarter ?? [])
      .filter((b) => b.reduction + b.avoidance > 0)
      .map((b) => ({ label: fyq(b.fiscal_year, b.fiscal_quarter), value: num(b.reduction), value2: num(b.avoidance) })),
    [kpis],
  );

  async function doAttest(id: string) {
    setActioning(id);
    try { const u = await attestSavings(id); setRecords((p) => p.map((r) => r.record_id === id ? u : r)); getSavingsKpis().then(setKpis).catch(() => {}); }
    catch (e) { alert(e instanceof Error ? e.message : "Attest failed"); }
    finally { setActioning(null); }
  }
  async function doReject() {
    if (!rejectingId || !rejectReason.trim()) return;
    setActioning(rejectingId);
    try { const u = await rejectSavings(rejectingId, rejectReason.trim()); setRecords((p) => p.map((r) => r.record_id === rejectingId ? u : r)); setRejectingId(null); setRejectReason(""); getSavingsKpis().then(setKpis).catch(() => {}); }
    catch (e) { alert(e instanceof Error ? e.message : "Reject failed"); }
    finally { setActioning(null); }
  }

  function resetForm() {
    setArtifact(null); setArtifactQuery(""); setArtifactResults([]);
    setSavingsType(""); setSavingsAmount(""); setBaselineContext(""); setFormError(null);
  }
  async function doSubmit() {
    setFormError(null);
    if (!artifact) { setFormError("Pick a sourcing event or contract first."); return; }
    const typeDef = SAVINGS_TYPES.find((t) => t.key === savingsType);
    if (!typeDef) { setFormError("Choose a savings type."); return; }
    const amt = Number(savingsAmount);
    if (!Number.isFinite(amt) || amt <= 0) { setFormError("Enter a positive savings amount."); return; }
    setSubmitting(true);
    try {
      await submitSavings({
        artifact_type: artifact.artifact_type,
        artifact_id: artifact.artifact_id,
        artifact_title: artifact.title,
        savings_class: typeDef.cls,
        savings_type: typeDef.key,
        supplier_id: artifact.supplier_id,
        supplier_name: artifact.supplier_name,
        segment_code: artifact.segment_code,
        fiscal_year: artifact.fiscal_year ?? new Date().getUTCFullYear(),
        fiscal_quarter: artifact.fiscal_quarter ?? (Math.floor(new Date().getUTCMonth() / 3) + 1),
        baseline_amount_usd: artifact.baseline_amount,
        savings_amount_usd: amt,
        baseline_context: baselineContext || null,
      });
      setFormOpen(false); resetForm(); reload();
    } catch (e) {
      setFormError(e instanceof Error ? e.message : "Submit failed");
    } finally { setSubmitting(false); }
  }

  return (
    <div style={{ position: "relative", flex: 1, overflow: "auto", padding: "var(--space-6)" }}>
      <BlobBg />
      <div style={{ position: "relative", zIndex: 1, maxWidth: 1280 }}>
        <PageHero
          eyebrow="Procurement"
          title="Savings Register"
          subtitle="Every cost reduction (hard) and cost avoidance (soft) logged against a sourcing event or contract, then attested by a second person. Attested savings count toward the headline."
          right={<PrimaryBtn onClick={() => { setFormOpen((o) => !o); resetForm(); }}>{formOpen ? "Close" : "Log savings +"}</PrimaryBtn>}
        />

        {/* KPI strip */}
        <div style={{ display: "flex", gap: "var(--space-4)", marginBottom: "var(--space-5)", flexWrap: "wrap" }}>
          <StatTile label="Attested Savings" value={kpis ? fmtUSD(kpis.attested_total, true) : "…"} accent="var(--db-green-700)" sub="verified, in register" />
          <StatTile label="Pending Attestation" value={kpis ? fmtUSD(kpis.pending_total, true) : "…"} accent="var(--db-yellow-600)" sub={kpis ? `${kpis.pending_count} awaiting review` : ""} />
          <StatTile label="Hard (Reduction)" value={kpis ? fmtUSD(kpis.hard_total, true) : "…"} accent="var(--db-lava-600)" sub="cash savings" />
          <StatTile label="Soft (Avoidance)" value={kpis ? fmtUSD(kpis.soft_total, true) : "…"} accent="var(--db-navy-800)" sub="cost avoided" />
          <StatTile label="Savings % of Addressable" value={kpis ? fmtPct(kpis.savings_pct_of_addressable) : "…"} sub="attested vs addressable spend" />
        </div>

        {/* Log savings form */}
        {formOpen && (
          <Card style={{ marginBottom: "var(--space-5)" }} accent="var(--db-lava-600)">
            <h3 style={{ fontSize: "var(--fs-h4)", fontWeight: 700, marginBottom: "var(--space-3)" }}>Log a savings record</h3>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)" }}>
              {/* Artifact picker */}
              <div>
                <div style={{ ...detailLabel, marginBottom: 6 }}>1. Tie to an artifact (sourcing event or contract)</div>
                {artifact ? (
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", padding: "var(--space-3)", background: "var(--bg-subtle)" }}>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600 }}>{artifact.title ?? artifact.artifact_id}</div>
                      <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)" }}>
                        {artifact.artifact_type === "contract" ? "Contract" : "Sourcing event"} · {artifact.artifact_id} · {artifact.supplier_name ?? "—"}
                      </div>
                    </div>
                    <button onClick={() => setArtifact(null)} style={{ background: "none", border: "none", color: "var(--fg-3)", cursor: "pointer", fontSize: 16 }}>×</button>
                  </div>
                ) : (
                  <>
                    <input
                      value={artifactQuery}
                      onChange={(e) => setArtifactQuery(e.target.value)}
                      placeholder="Search by event, contract title, or supplier…"
                      style={{ width: "100%", padding: "var(--space-2) var(--space-3)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", fontFamily: "var(--font-sans)", fontSize: 13 }}
                    />
                    {artifactResults.length > 0 && (
                      <div style={{ marginTop: 6, maxHeight: 180, overflowY: "auto", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)" }}>
                        {artifactResults.map((a) => (
                          <div key={`${a.artifact_type}-${a.artifact_id}`} onClick={() => { setArtifact(a); setArtifactResults([]); }}
                            style={{ padding: "var(--space-2) var(--space-3)", cursor: "pointer", borderBottom: "1px solid var(--border)", fontSize: 12 }}>
                            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: a.artifact_type === "contract" ? "var(--db-navy-800)" : "var(--db-lava-600)", marginRight: 6 }}>
                              {a.artifact_type === "contract" ? "CONTRACT" : "EVENT"}
                            </span>
                            {a.title ?? a.artifact_id} <span style={{ color: "var(--fg-3)" }}>· {a.supplier_name ?? "—"}</span>
                          </div>
                        ))}
                      </div>
                    )}
                  </>
                )}
              </div>
              {/* Type + amount */}
              <div>
                <div style={{ ...detailLabel, marginBottom: 6 }}>2. Savings type & amount</div>
                <select value={savingsType} onChange={(e) => setSavingsType(e.target.value)}
                  style={{ width: "100%", padding: "var(--space-2) var(--space-3)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", fontSize: 13, marginBottom: "var(--space-2)" }}>
                  <option value="">Select a savings type…</option>
                  <optgroup label="Cost Reduction (hard)">
                    {SAVINGS_TYPES.filter((t) => t.cls === "reduction").map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                  </optgroup>
                  <optgroup label="Cost Avoidance (soft)">
                    {SAVINGS_TYPES.filter((t) => t.cls === "avoidance").map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
                  </optgroup>
                </select>
                <input type="number" value={savingsAmount} onChange={(e) => setSavingsAmount(e.target.value)} placeholder="Savings amount (USD)"
                  style={{ width: "100%", padding: "var(--space-2) var(--space-3)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", fontFamily: "var(--font-mono)", fontSize: 13, marginBottom: "var(--space-2)" }} />
                <textarea value={baselineContext} onChange={(e) => setBaselineContext(e.target.value)} placeholder="Baseline context (how was the saving measured?)" rows={2}
                  style={{ width: "100%", padding: "var(--space-2) var(--space-3)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", fontFamily: "var(--font-sans)", fontSize: 13, resize: "vertical" }} />
              </div>
            </div>
            {formError && <div style={{ color: "var(--danger)", fontSize: 12, marginTop: "var(--space-2)" }}>{formError}</div>}
            <div style={{ display: "flex", gap: "var(--space-2)", marginTop: "var(--space-3)" }}>
              <PrimaryBtn onClick={doSubmit} disabled={submitting}>{submitting ? "Submitting…" : "Submit for attestation"}</PrimaryBtn>
              <SecondaryBtn onClick={() => { setFormOpen(false); resetForm(); }}>Cancel</SecondaryBtn>
            </div>
          </Card>
        )}

        {/* By-quarter attested hard/soft */}
        {quarterBars.length > 0 && (
          <Card style={{ marginBottom: "var(--space-5)" }}>
            <h3 style={{ fontSize: "var(--fs-h4)", fontWeight: 700, marginBottom: "var(--space-1)" }}>Attested savings by quarter</h3>
            <p style={{ fontSize: "var(--fs-body-sm)", color: "var(--fg-2)", marginBottom: "var(--space-4)" }}>Hard (cost reduction) vs soft (cost avoidance), attested only.</p>
            <BarChart data={quarterBars} color="var(--db-lava-600)" color2="var(--db-navy-800)" label1="Reduction" label2="Avoidance" formatValue={(v) => fmtUSD(v, true)} width={1180} height={Math.max(180, quarterBars.length * 30 + 24)} />
          </Card>
        )}

        {/* Filters */}
        <div style={{ display: "flex", gap: "var(--space-2)", marginBottom: "var(--space-3)", flexWrap: "wrap" }}>
          {(["", "pending", "attested", "rejected"] as const).map((s) => (
            <Pill key={s || "all"} active={statusFilter === s} onClick={() => setStatusFilter(s)}>{s ? STATUS_TONE[s].label : "All status"}</Pill>
          ))}
          <span style={{ width: 1, background: "var(--border)", margin: "0 var(--space-2)" }} />
          {(["", "reduction", "avoidance"] as const).map((c) => (
            <Pill key={c || "allc"} active={classFilter === c} onClick={() => setClassFilter(c)}>{c ? CLASS_LABEL[c] : "All types"}</Pill>
          ))}
        </div>

        {/* Register table */}
        <Card padding="0">
          {loading ? (
            <div style={{ padding: "var(--space-7)", textAlign: "center", color: "var(--fg-3)" }}>Loading…</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ minWidth: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)" }}>
                    {["Artifact", "Supplier", "Class", "Type", "Savings", "Period", "Status"].map((h) => (
                      <th key={h} style={th}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => {
                    const isOpen = selected === r.record_id;
                    const cls = STATUS_TONE[r.status];
                    return (
                      <React.Fragment key={r.record_id}>
                        <tr onClick={() => setSelected(isOpen ? null : r.record_id)}
                          style={{ borderBottom: isOpen ? "none" : "1px solid var(--border)", background: isOpen ? "var(--bg-subtle)" : "transparent", cursor: "pointer" }}>
                          <td style={{ ...cell, maxWidth: 240 }}>
                            <div style={{ fontSize: 13, fontWeight: 500, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: isOpen ? "var(--db-lava-600)" : undefined }}>{r.artifact_title ?? r.artifact_id}</div>
                            <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)" }}>{r.artifact_type === "contract" ? "Contract" : "Event"} · {r.artifact_id}</div>
                          </td>
                          <td style={{ ...cell, fontSize: 12, color: "var(--fg-2)" }}>{r.supplier_name ?? "—"}</td>
                          <td style={cell}><Pill>{CLASS_LABEL[r.savings_class]}</Pill></td>
                          <td style={{ ...cell, fontSize: 12, maxWidth: 220, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{SAVINGS_TYPE_LABEL[r.savings_type] ?? r.savings_type}</td>
                          <td style={{ ...cell, fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 600 }}>{fmtUSD(num(r.savings_amount_usd), true)}</td>
                          <td style={{ ...cell, fontFamily: "var(--font-mono)", fontSize: 12 }}>{fyq(r.fiscal_year, r.fiscal_quarter)}</td>
                          <td style={cell}><StatusChip status={r.status} /></td>
                        </tr>
                        {isOpen && (
                          <tr style={{ borderBottom: "1px solid var(--border)" }}>
                            <td colSpan={7} style={{ padding: 0 }}>
                              <div style={{ background: "var(--bg-subtle)", borderTop: `2px solid ${cls.color}`, padding: "var(--space-5)" }}>
                                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: "var(--space-5)", marginBottom: "var(--space-4)" }}>
                                  <div>
                                    <div style={detailLabel}>Artifact</div>
                                    <div style={{ fontSize: 13, marginTop: 2 }}>{r.artifact_title ?? r.artifact_id}</div>
                                    <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)" }}>{r.artifact_type === "contract" ? "Contract" : "Sourcing event"} · {r.artifact_id}</div>
                                  </div>
                                  <div>
                                    <div style={detailLabel}>Savings type</div>
                                    <div style={{ fontSize: 13, marginTop: 2 }}>{SAVINGS_TYPE_LABEL[r.savings_type] ?? r.savings_type}</div>
                                    <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)" }}>{CLASS_LABEL[r.savings_class]}</div>
                                  </div>
                                  <div>
                                    <div style={detailLabel}>Baseline → Realized → Savings</div>
                                    <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, marginTop: 2 }}>
                                      {fmtUSD(r.baseline_amount_usd, true)} → {fmtUSD(r.realized_amount_usd, true)} → <strong style={{ color: cls.color }}>{fmtUSD(num(r.savings_amount_usd), true)}</strong>
                                    </div>
                                  </div>
                                </div>
                                {r.baseline_context && <div style={{ fontSize: 13, color: "var(--fg-2)", marginBottom: "var(--space-4)" }}>{r.baseline_context}</div>}
                                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-end", flexWrap: "wrap", gap: "var(--space-3)" }}>
                                  <div style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)" }}>
                                    Submitted by <span style={{ color: "var(--fg-1)" }}>{r.submitted_by}</span> · {fmtDate(r.submitted_at)}
                                    {r.status === "attested" && r.attested_by && <> · attested by <span style={{ color: "var(--db-green-700)" }}>{r.attested_by}</span></>}
                                    {r.status === "rejected" && r.rejection_reason && <> · rejected: <span style={{ color: "var(--danger)" }}>{r.rejection_reason}</span></>}
                                  </div>
                                  {r.status === "pending" && (
                                    rejectingId === r.record_id ? (
                                      <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
                                        <input value={rejectReason} onChange={(e) => setRejectReason(e.target.value)} placeholder="Rejection reason"
                                          style={{ padding: "var(--space-2) var(--space-3)", border: "1px solid var(--border)", borderRadius: "var(--radius-sm)", fontSize: 12, minWidth: 220 }} />
                                        <SecondaryBtn onClick={doReject} disabled={actioning === r.record_id || !rejectReason.trim()}>Confirm reject</SecondaryBtn>
                                        <SecondaryBtn onClick={() => { setRejectingId(null); setRejectReason(""); }}>Cancel</SecondaryBtn>
                                      </div>
                                    ) : (
                                      <div style={{ display: "flex", gap: "var(--space-2)", alignItems: "center" }}>
                                        {r.submitted_by.toLowerCase() === me.toLowerCase() && (
                                          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--fg-3)" }}>you submitted this — a different person must attest</span>
                                        )}
                                        <PrimaryBtn onClick={() => doAttest(r.record_id)} disabled={actioning === r.record_id || r.submitted_by.toLowerCase() === me.toLowerCase()}>Attest</PrimaryBtn>
                                        <SecondaryBtn onClick={() => { setRejectingId(r.record_id); setRejectReason(""); }}>Reject</SecondaryBtn>
                                      </div>
                                    )
                                  )}
                                </div>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                    );
                  })}
                  {rows.length === 0 && (
                    <tr><td colSpan={7} style={{ ...cell, color: "var(--fg-3)" }}>No savings records match.</td></tr>
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
