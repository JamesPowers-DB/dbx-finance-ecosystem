import React, { useEffect, useState } from "react";
import { BlobBg } from "../components/layout/BlobBg";
import { PageHero } from "../components/layout/PageHero";
import { Card } from "../components/layout/Card";
import { StatTile } from "../components/StatTile";
import { SegSelect } from "../components/Buttons";
import { HistogramChart } from "../charts/HistogramChart";
import { SparklineChart } from "../charts/SparklineChart";
import {
  getLabelingCoverage, getConfidenceDistribution,
  getDisagreements, getModelHistory,
} from "../api";
import { fmtPct, fmtInt, fmtDate } from "../format";
import type { ConfidenceBucket, DisagreementRow, LabelingCoverageRow, ModelHistoryRow } from "../types";

export function LabelingMonitor({ searchQuery = "" }: { searchQuery?: string }) {
  const [coverage, setCoverage] = useState<LabelingCoverageRow[]>([]);
  const [confidence, setConfidence] = useState<ConfidenceBucket[]>([]);
  const [disagreements, setDisagreements] = useState<DisagreementRow[]>([]);
  const [history, setHistory] = useState<ModelHistoryRow[]>([]);
  const [tier, setTier] = useState<"primary" | "secondary">("secondary");
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"coverage" | "confidence" | "disagreements" | "history">("coverage");

  useEffect(() => {
    Promise.all([
      getLabelingCoverage(),
      getConfidenceDistribution(tier),
      getDisagreements(),
      getModelHistory(),
    ])
      .then(([cov, conf, dis, hist]) => {
        setCoverage(cov); setConfidence(conf);
        setDisagreements(dis); setHistory(hist);
      })
      .finally(() => setLoading(false));
  }, [tier]);

  const avgCoverage = coverage.length
    ? coverage.reduce((a, r) => a + r.coverage_pct, 0) / coverage.length
    : 0;
  const totalClassified = coverage.reduce((a, r) => a + r.classified_lines, 0);
  const totalLines = coverage.reduce((a, r) => a + r.total_lines, 0);

  const histValues = history.map((h) => h.holdout_leaf_accuracy ?? 0);

  return (
    <div style={{ position: "relative", flex: 1, overflow: "auto", padding: "var(--space-6)" }}>
      <BlobBg />
      <div style={{ position: "relative", zIndex: 1, maxWidth: 1200 }}>
        <PageHero
          eyebrow="Review"
          title="Spend Labeling Monitor"
          subtitle="ML classification coverage, confidence distributions, model disagreements, and evaluation history."
          right={
            <SegSelect
              options={[
                { label: "Coverage", value: "coverage" },
                { label: "Confidence", value: "confidence" },
                { label: "Disagreements", value: "disagreements" },
                { label: "Model History", value: "history" },
              ]}
              value={view}
              onChange={(v) => setView(v as typeof view)}
            />
          }
        />

        {/* KPI strip */}
        <div style={{ display: "flex", gap: "var(--space-4)", marginBottom: "var(--space-6)", flexWrap: "wrap" }}>
          <StatTile label="Avg Coverage" value={fmtPct(avgCoverage)} accent="var(--db-lava-600)" sub="classified / total" />
          <StatTile label="Total Classified" value={fmtInt(totalClassified)} accent="var(--db-navy-800)" />
          <StatTile label="Total Lines" value={fmtInt(totalLines)} accent="var(--db-gray-nav)" />
          <StatTile label="Disagreements" value={fmtInt(disagreements.length)} accent="var(--warning)" sub="low-confidence errors" />
        </div>

        {/* Coverage table */}
        {view === "coverage" && (
          <Card padding="0">
            {loading ? (
              <div style={{ padding: "var(--space-7)", textAlign: "center", color: "var(--fg-3)" }}>Loading…</div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)" }}>
                    {["Segment", "Period", "Total Lines", "Classified", "Coverage %"].map((h) => (
                      <th key={h} style={{ padding: "var(--space-3) var(--space-4)", textAlign: "left",
                        fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)",
                        fontWeight: 500, textTransform: "uppercase" }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {coverage.map((r) => (
                    <tr key={`${r.segment_code}-${r.fiscal_year}-${r.fiscal_quarter}`}
                      style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "var(--space-3) var(--space-4)", fontSize: 13 }}>{r.segment_code}</td>
                      <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
                        FY{String(r.fiscal_year).slice(-2)} Q{r.fiscal_quarter}
                      </td>
                      <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                        {fmtInt(r.total_lines)}
                      </td>
                      <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                        {fmtInt(r.classified_lines)}
                      </td>
                      <td style={{ padding: "var(--space-3) var(--space-4)" }}>
                        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)" }}>
                          <div style={{ width: 80, height: 6, background: "var(--bg-subtle)", borderRadius: 3 }}>
                            <div style={{ width: `${r.coverage_pct}%`, height: "100%",
                              background: r.coverage_pct > 80 ? "var(--success)" : r.coverage_pct > 50 ? "var(--warning)" : "var(--danger)",
                              borderRadius: 3 }} />
                          </div>
                          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11 }}>
                            {fmtPct(r.coverage_pct)}
                          </span>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
        )}

        {/* Confidence histograms */}
        {view === "confidence" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-5)" }}>
            <div style={{ display: "flex", alignItems: "center", gap: "var(--space-3)", marginBottom: "var(--space-2)" }}>
              <SegSelect
                options={[{ label: "Leaf (secondary)", value: "secondary" }, { label: "Parent (primary)", value: "primary" }]}
                value={tier}
                onChange={(v) => setTier(v as "primary" | "secondary")}
              />
            </div>
            <Card>
              <h3 style={{ fontSize: "var(--fs-body)", fontWeight: 700, marginBottom: "var(--space-4)" }}>
                Confidence Distribution — {tier === "secondary" ? "Leaf (secondary)" : "Parent (primary)"}
              </h3>
              {loading ? (
                <div style={{ color: "var(--fg-3)", textAlign: "center" }}>Loading…</div>
              ) : (
                <HistogramChart data={confidence} width={700} height={200} referenceAt={0.75} />
              )}
              <p style={{ fontSize: 12, color: "var(--fg-3)", marginTop: "var(--space-3)" }}>
                Dashed line at 0.75 — managed_spend_flag threshold. Lines left of the threshold are unclassified or low-confidence.
              </p>
            </Card>
          </div>
        )}

        {/* Disagreements */}
        {view === "disagreements" && (() => {
          const q = searchQuery.toLowerCase();
          const filteredDisagreements = q
            ? disagreements.filter(
                (d) =>
                  d.supplier_name?.toLowerCase().includes(q) ||
                  d.line_description?.toLowerCase().includes(q) ||
                  d.true_category_secondary?.toLowerCase().includes(q) ||
                  d.predicted_secondary_category?.toLowerCase().includes(q) ||
                  d.segment_code?.toLowerCase().includes(q),
              )
            : disagreements;
          return (
          <Card padding="0">
            {loading ? (
              <div style={{ padding: "var(--space-7)", textAlign: "center", color: "var(--fg-3)" }}>Loading…</div>
            ) : filteredDisagreements.length === 0 ? (
              <div style={{ padding: "var(--space-7)", textAlign: "center", color: "var(--fg-3)" }}>
                {disagreements.length === 0 ? "No disagreements found. Run batch inference first." : `No results for "${searchQuery}"`}
              </div>
            ) : (
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border)" }}>
                    {["Date", "Supplier", "Description", "Amount", "True Label", "Predicted", "Confidence"].map((h) => (
                      <th key={h} style={{ padding: "var(--space-3) var(--space-4)", textAlign: "left",
                        fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)",
                        fontWeight: 500, textTransform: "uppercase" }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredDisagreements.map((d) => (
                    <tr key={d.invoice_line_id} style={{ borderBottom: "1px solid var(--border)" }}>
                      <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
                        {fmtDate(d.invoice_date)}
                      </td>
                      <td style={{ padding: "var(--space-3) var(--space-4)", fontSize: 13 }}>{d.supplier_name ?? "—"}</td>
                      <td style={{ padding: "var(--space-3) var(--space-4)", fontSize: 12, color: "var(--fg-2)",
                        maxWidth: 200, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                        {d.line_description ?? "—"}
                      </td>
                      <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                        ${d.amount?.toLocaleString() ?? "—"}
                      </td>
                      <td style={{ padding: "var(--space-3) var(--space-4)", fontSize: 12, color: "var(--success)" }}>
                        {d.true_category_secondary}
                      </td>
                      <td style={{ padding: "var(--space-3) var(--space-4)", fontSize: 12, color: "var(--danger)" }}>
                        {d.predicted_secondary_category}
                      </td>
                      <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12,
                        color: (d.secondary_confidence ?? 1) < 0.5 ? "var(--danger)" : "var(--fg-2)" }}>
                        {d.secondary_confidence != null ? Number(d.secondary_confidence).toFixed(3) : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </Card>
          );
        })()}

        {/* Model history */}
        {view === "history" && (
          <div style={{ display: "flex", flexDirection: "column", gap: "var(--space-4)" }}>
            {loading ? (
              <div style={{ textAlign: "center", color: "var(--fg-3)", padding: "var(--space-7)" }}>Loading…</div>
            ) : history.length === 0 ? (
              <div style={{ textAlign: "center", color: "var(--fg-3)", padding: "var(--space-7)" }}>
                No eval runs yet. Run the train_spend_classifier job to populate.
              </div>
            ) : (
              <Card>
                <h3 style={{ fontSize: "var(--fs-body)", fontWeight: 700, marginBottom: "var(--space-4)" }}>
                  Model Evaluation History
                </h3>
                <div style={{ display: "flex", gap: "var(--space-6)", marginBottom: "var(--space-5)" }}>
                  <div>
                    <p style={{ fontSize: 12, color: "var(--fg-3)", marginBottom: "var(--space-2)" }}>
                      Holdout Leaf Accuracy
                    </p>
                    <SparklineChart
                      values={histValues}
                      width={180}
                      height={44}
                      color="var(--db-lava-600)"
                      showDots
                    />
                  </div>
                  <div>
                    <p style={{ fontSize: 12, color: "var(--fg-3)", marginBottom: "var(--space-2)" }}>
                      Maverick Leaf Accuracy
                    </p>
                    <SparklineChart
                      values={history.map((h) => h.maverick_leaf_accuracy ?? 0)}
                      width={180}
                      height={44}
                      color="var(--db-navy-800)"
                      showDots
                    />
                  </div>
                </div>
                <table style={{ width: "100%", borderCollapse: "collapse" }}>
                  <thead>
                    <tr style={{ borderBottom: "1px solid var(--border)" }}>
                      {["Alias", "Eval Date", "Holdout Leaf", "Maverick Leaf", "Holdout Parent"].map((h) => (
                        <th key={h} style={{ padding: "var(--space-3) var(--space-4)", textAlign: "left",
                          fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--fg-3)",
                          fontWeight: 500, textTransform: "uppercase" }}>
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {history.map((h, i) => (
                      <tr key={i} style={{ borderBottom: "1px solid var(--border)" }}>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12,
                          color: "var(--db-lava-600)", fontWeight: 600 }}>
                          {h.model_alias ?? "—"}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 11 }}>
                          {fmtDate(h.eval_date)}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                          {fmtPct(h.holdout_leaf_accuracy != null ? h.holdout_leaf_accuracy * 100 : null)}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                          {fmtPct(h.maverick_leaf_accuracy != null ? h.maverick_leaf_accuracy * 100 : null)}
                        </td>
                        <td style={{ padding: "var(--space-3) var(--space-4)", fontFamily: "var(--font-mono)", fontSize: 12 }}>
                          {fmtPct(h.holdout_parent_accuracy != null ? h.holdout_parent_accuracy * 100 : null)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </Card>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
