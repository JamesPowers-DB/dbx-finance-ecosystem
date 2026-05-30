import React, { useEffect, useMemo, useState } from "react";
import { BlobBg } from "../components/layout/BlobBg";
import { PageHero } from "../components/layout/PageHero";
import { Card } from "../components/layout/Card";
import { StatTile } from "../components/StatTile";
import { SegSelect } from "../components/Buttons";
import { BarChart } from "../charts/BarChart";
import { SpendTrendChart } from "../charts/SpendTrendChart";
import { fmtUSD, fmtPct, fmtInt, fmtDays } from "../format";
import {
  getSpendComposition,
  getManagedStatus,
  getSpendTrend,
  getSupplierConcentration,
} from "../api";
import type {
  SpendCompositionRow,
  ManagedStatusResponse,
  SpendTrendRow,
  SupplierConcentrationRow,
} from "../types";

type Dim = "category" | "segment" | "pr_source";

const DIM_OPTIONS = [
  { label: "Category", value: "category" },
  { label: "Segment", value: "segment" },
  { label: "PR Source", value: "pr_source" },
];

const th: React.CSSProperties = {
  textAlign: "left",
  padding: "8px 12px",
  fontFamily: "var(--font-mono)",
  fontSize: 11,
  textTransform: "uppercase",
  letterSpacing: "0.04em",
  color: "var(--fg-2)",
  borderBottom: "1px solid var(--border)",
  whiteSpace: "nowrap",
};
const td: React.CSSProperties = {
  padding: "8px 12px",
  fontSize: 13,
  color: "var(--fg-1)",
  borderBottom: "1px solid var(--border)",
  whiteSpace: "nowrap",
};
const num: React.CSSProperties = { ...td, textAlign: "right", fontFamily: "var(--font-mono)" };

const sectionTitle: React.CSSProperties = {
  fontSize: "var(--fs-h4)",
  fontWeight: 700,
  marginBottom: "var(--space-1)",
};
const sectionSub: React.CSSProperties = {
  fontSize: "var(--fs-body-sm)",
  color: "var(--fg-2)",
  marginBottom: "var(--space-4)",
};

export function Analytics() {
  const [dim, setDim] = useState<Dim>("category");
  const [composition, setComposition] = useState<SpendCompositionRow[]>([]);
  const [managed, setManaged] = useState<ManagedStatusResponse | null>(null);
  const [trend, setTrend] = useState<SpendTrendRow[]>([]);
  const [concentration, setConcentration] = useState<SupplierConcentrationRow[]>([]);

  useEffect(() => {
    getManagedStatus().then(setManaged).catch(() => setManaged(null));
    getSpendTrend().then(setTrend).catch(() => setTrend([]));
    getSupplierConcentration(20).then(setConcentration).catch(() => setConcentration([]));
  }, []);

  useEffect(() => {
    getSpendComposition(dim).then(setComposition).catch(() => setComposition([]));
  }, [dim]);

  const compositionBars = useMemo(
    () =>
      composition.slice(0, 10).map((r) => ({
        label: r.label ?? "Unknown",
        value: r.managed_spend,
        value2: Math.max(r.total_spend - r.managed_spend, 0),
      })),
    [composition],
  );

  const quadrantBars = useMemo(
    () =>
      (managed?.quadrants ?? []).map((q) => ({
        label: q.managed_status,
        value: q.spend,
      })),
    [managed],
  );

  const trendPoints = useMemo(
    () =>
      trend.map((t) => ({
        period: `FY${String(t.fiscal_year).slice(2)} Q${t.fiscal_quarter}`,
        total_spend: t.total_spend,
        managed_spend: t.managed_spend,
      })),
    [trend],
  );

  return (
    <div style={{ position: "relative", flex: 1, overflow: "auto", padding: "var(--space-6)" }}>
      <BlobBg />
      <div style={{ position: "relative", zIndex: 1, maxWidth: 1100, margin: "0 auto" }}>
        <PageHero
          eyebrow="Analytics"
          title="Spend Analytics"
          subtitle="Managed-spend lineage, composition, and supplier concentration — all from the governed mv_spend metric views."
        />

        {/* Managed-spend headline: $ vs count divergence */}
        <div style={{ display: "flex", gap: "var(--space-4)", marginBottom: "var(--space-6)", flexWrap: "wrap" }}>
          <StatTile
            label="Managed Spend ($)"
            value={managed ? fmtPct(managed.managed_pct) : "…"}
            accent="var(--db-green-700)"
            sub="contracted or sourced, by dollars"
          />
          <StatTile
            label="Managed Spend (by count)"
            value={managed ? fmtPct(managed.managed_pct_count) : "…"}
            accent="var(--db-navy-800)"
            sub="by invoice-line count"
          />
          <StatTile
            label="$ vs count gap"
            value={managed ? `${(managed.managed_pct - managed.managed_pct_count).toFixed(1)} pts` : "…"}
            accent="var(--db-yellow-600)"
            sub="managed spend = few large buys"
          />
        </div>

        {/* Composition */}
        <Card style={{ marginBottom: "var(--space-5)" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "var(--space-3)" }}>
            <div>
              <h3 style={sectionTitle}>Spend composition</h3>
              <p style={sectionSub}>T12M paid spend, managed (filled) vs unmanaged tail.</p>
            </div>
            <SegSelect options={DIM_OPTIONS} value={dim} onChange={(v) => setDim(v as Dim)} />
          </div>
          {compositionBars.length > 0 ? (
            <BarChart
              data={compositionBars}
              color="var(--db-green-700)"
              color2="var(--db-navy-400)"
              label1="Managed"
              label2="Unmanaged"
              formatValue={(v) => fmtUSD(v, true)}
              width={1000}
              height={Math.max(160, compositionBars.length * 30 + 24)}
            />
          ) : (
            <p style={sectionSub}>No data.</p>
          )}
        </Card>

        {/* Trend */}
        <Card style={{ marginBottom: "var(--space-5)" }}>
          <h3 style={sectionTitle}>Spend trend</h3>
          <p style={sectionSub}>Paid spend by fiscal quarter, with the managed-spend overlay.</p>
          {trendPoints.length > 0 ? (
            <SpendTrendChart points={trendPoints} width={1000} height={260} />
          ) : (
            <p style={sectionSub}>No data.</p>
          )}
        </Card>

        {/* Managed status quadrant */}
        <Card style={{ marginBottom: "var(--space-5)" }}>
          <h3 style={sectionTitle}>Managed status</h3>
          <p style={sectionSub}>
            Sourcing-management quadrant by paid spend: contracted &amp; sourced, contract-only,
            sourced-only, or the unmanaged tail.
          </p>
          {quadrantBars.length > 0 ? (
            <BarChart
              data={quadrantBars}
              color="var(--db-lava-600)"
              formatValue={(v) => fmtUSD(v, true)}
              width={1000}
              height={170}
            />
          ) : (
            <p style={sectionSub}>No data.</p>
          )}
        </Card>

        {/* Supplier concentration */}
        <Card>
          <h3 style={sectionTitle}>Supplier concentration</h3>
          <p style={sectionSub}>Top 20 suppliers by T12M spend; cumulative % shows tail concentration.</p>
          <div style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", minWidth: "100%" }}>
              <thead>
                <tr>
                  <th style={th}>#</th>
                  <th style={th}>Supplier</th>
                  <th style={{ ...th, textAlign: "right" }}>T12M Spend</th>
                  <th style={{ ...th, textAlign: "right" }}>Cumulative %</th>
                  <th style={{ ...th, textAlign: "right" }}>Managed %</th>
                  <th style={{ ...th, textAlign: "right" }}>Maverick %</th>
                  <th style={{ ...th, textAlign: "right" }}>Avg DPO</th>
                </tr>
              </thead>
              <tbody>
                {concentration.map((r, i) => (
                  <tr key={r.supplier_id}>
                    <td style={{ ...num, color: "var(--fg-3)" }}>{i + 1}</td>
                    <td style={td}>{r.supplier_name ?? r.supplier_id}</td>
                    <td style={num}>{fmtUSD(r.trailing_spend, true)}</td>
                    <td style={num}>{fmtPct(r.cumulative_pct)}</td>
                    <td style={num}>{fmtPct(r.managed_spend_pct)}</td>
                    <td style={num}>{fmtPct(r.measured_maverick_pct)}</td>
                    <td style={num}>{fmtDays(r.avg_dpo)}</td>
                  </tr>
                ))}
                {concentration.length === 0 && (
                  <tr><td style={td} colSpan={7}>No data.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}
