import React, { useEffect, useMemo, useState } from "react";
import { BlobBg } from "../components/layout/BlobBg";
import { PageHero } from "../components/layout/PageHero";
import { Card } from "../components/layout/Card";
import { StatTile } from "../components/StatTile";
import { SegSelect } from "../components/Buttons";
import { BarChart } from "../charts/BarChart";
import { SpendTrendChart } from "../charts/SpendTrendChart";
import { FunnelChart } from "../charts/FunnelChart";
import { ParetoChart } from "../charts/ParetoChart";
import { fmtUSD, fmtPct, fmtInt, fmtDays } from "../format";
import {
  getAnalyticsKpis,
  getLifecycleFunnel,
  getSpendComposition,
  getCompositionDetail,
  getSpendTrend,
  getSupplierConcentration,
} from "../api";
import type {
  AnalyticsKpis,
  CompositionDetailRow,
  DateRange,
  LifecycleFunnelRow,
  SpendCompositionRow,
  SpendTrendRow,
  SupplierConcentrationRow,
  TrendGrain,
} from "../types";

type Dim = "category" | "segment" | "pr_source";

interface AnalyticsProps {
  onNavigate?: (page: string, opts?: { supplierId?: string }) => void;
}

const DIM_OPTIONS = [
  { label: "Category", value: "category" },
  { label: "Segment", value: "segment" },
  { label: "PR Source", value: "pr_source" },
];

const GRAIN_OPTIONS = [
  { label: "Daily", value: "daily" },
  { label: "Weekly", value: "weekly" },
  { label: "Monthly", value: "monthly" },
  { label: "Quarterly", value: "quarterly" },
];

const RANGE_OPTIONS = [
  { label: "90D", value: "90d" },
  { label: "T12M", value: "t12m" },
  { label: "T24M", value: "t24m" },
  { label: "All", value: "all" },
];

const RANGE_DAYS: Record<DateRange, number | null> = { "90d": 90, t12m: 365, t24m: 730, all: null };

const MON = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Format a DATE_TRUNC'd ISO period into a compact axis label for the grain. */
function fmtPeriod(iso: string, grain: TrendGrain): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const mo = d.getUTCMonth();
  const yr = String(d.getUTCFullYear()).slice(2);
  if (grain === "daily" || grain === "weekly") return `${mo + 1}/${d.getUTCDate()}`;
  if (grain === "monthly") return `${MON[mo]} '${yr}`;
  return `Q${Math.floor(mo / 3) + 1} '${yr}`;
}

/** Human label for the active window (mirrors the SQL CURRENT_DATE() lookback). */
function rangeLabel(range: DateRange): string {
  const days = RANGE_DAYS[range];
  if (days == null) return "Showing all time";
  const end = new Date();
  const start = new Date(end.getTime() - days * 86400000);
  const fmt = (d: Date) => `${MON[d.getMonth()]} ${d.getFullYear()}`;
  return `Showing ${fmt(start)} – ${fmt(end)}`;
}

const num = (v: unknown): number => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};

const slice2title = (v: string) => v.replace(/_/g, " ");

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
const tdNum: React.CSSProperties = { ...td, textAlign: "right", fontFamily: "var(--font-mono)" };

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

export function Analytics({ onNavigate }: AnalyticsProps) {
  const [range, setRange] = useState<DateRange>("t12m");
  const [kpis, setKpis] = useState<AnalyticsKpis | null>(null);
  const [funnel, setFunnel] = useState<LifecycleFunnelRow[]>([]);
  const [dim, setDim] = useState<Dim>("category");
  const [composition, setComposition] = useState<SpendCompositionRow[]>([]);
  const [grain, setGrain] = useState<TrendGrain>("monthly");
  const [trend, setTrend] = useState<SpendTrendRow[]>([]);
  const [concentration, setConcentration] = useState<SupplierConcentrationRow[]>([]);
  const [drill, setDrill] = useState<{ dim: Dim; value: string } | null>(null);
  const [drillRows, setDrillRows] = useState<CompositionDetailRow[]>([]);
  const [drillLoading, setDrillLoading] = useState(false);
  const [hoverRow, setHoverRow] = useState<string | null>(null);

  const launchSupplier = (supplierId: string) => onNavigate?.("suppliers", { supplierId });

  // Range drives every widget. Clear the drill when the window changes (the
  // slice's supplier list would be stale).
  useEffect(() => {
    getAnalyticsKpis(range).then(setKpis).catch(() => setKpis(null));
    getLifecycleFunnel(range).then(setFunnel).catch(() => setFunnel([]));
    getSupplierConcentration(20, range).then(setConcentration).catch(() => setConcentration([]));
    setDrill(null);
  }, [range]);

  useEffect(() => {
    getSpendComposition(dim, range).then(setComposition).catch(() => setComposition([]));
    setDrill(null);
  }, [dim, range]);

  useEffect(() => {
    getSpendTrend(grain, range).then(setTrend).catch(() => setTrend([]));
  }, [grain, range]);

  useEffect(() => {
    if (!drill) {
      setDrillRows([]);
      return;
    }
    setDrillLoading(true);
    getCompositionDetail(drill.dim, drill.value, range)
      .then(setDrillRows)
      .catch(() => setDrillRows([]))
      .finally(() => setDrillLoading(false));
  }, [drill, range]);

  const compositionBars = useMemo(
    () =>
      composition.slice(0, 10).map((r) => {
        const total = num(r.total_spend);
        const m = num(r.managed_spend);
        return { label: r.label ?? "Unknown", value: m, value2: Math.max(total - m, 0) };
      }),
    [composition],
  );

  const trendPoints = useMemo(
    () =>
      trend.map((t) => ({
        period: fmtPeriod(t.period, grain),
        total_spend: num(t.total_spend),
        managed_spend: num(t.managed_spend),
      })),
    [trend, grain],
  );

  const funnelStages = useMemo(
    () => funnel.map((f) => ({ ...f, amount: num(f.amount), leak: f.leak == null ? null : num(f.leak) })),
    [funnel],
  );

  const toggleDrill = (label: string) =>
    setDrill((cur) => (cur && cur.dim === dim && cur.value === label ? null : { dim, value: label }));

  return (
    <div style={{ position: "relative", flex: 1, overflow: "auto", padding: "var(--space-6)" }}>
      <BlobBg />
      <div style={{ position: "relative", zIndex: 1, maxWidth: 1280 }}>
        <PageHero
          eyebrow="Analytics"
          title="Spend Analytics"
          subtitle="From requisition to payment — where spend flows, where it leaks, and which suppliers to act on. Every number resolves from the governed mv_spend / mv_purchase_orders metric views."
          right={
            <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: "var(--space-2)" }}>
              <SegSelect options={RANGE_OPTIONS} value={range} onChange={(v) => setRange(v as DateRange)} />
              <span style={{ fontFamily: "var(--font-mono)", fontSize: "var(--fs-caption)", color: "var(--fg-3)" }}>
                {rangeLabel(range)}
              </span>
            </div>
          }
        />

        {/* KPI strip */}
        <div style={{ display: "flex", gap: "var(--space-4)", marginBottom: "var(--space-6)", flexWrap: "wrap" }}>
          <StatTile label="Total Spend" value={kpis ? fmtUSD(kpis.total_spend, true) : "…"} accent="var(--db-green-700)" sub="paid, in window" />
          <StatTile label="Addressable" value={kpis ? fmtUSD(kpis.addressable_spend, true) : "…"} accent="var(--db-navy-800)" sub="sourcing-eligible" />
          <StatTile label="Managed %" value={kpis ? fmtPct(kpis.managed_pct) : "…"} accent="var(--db-lava-600)" sub="of addressable $" />
          <StatTile label="On-Time Pay %" value={kpis ? fmtPct(kpis.on_time_pct) : "…"} accent="var(--db-yellow-600)" sub="invoices paid on terms" />
          <StatTile label="Avg Days-to-Pay" value={kpis ? fmtDays(kpis.avg_dpo) : "…"} sub="DPO across suppliers" />
          <StatTile label="Active Vendors" value={kpis ? fmtInt(kpis.active_suppliers) : "…"} sub="with paid spend" />
        </div>

        {/* Hero row: lifecycle funnel + interactive trend */}
        <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 5fr) minmax(0, 7fr)", gap: "var(--space-5)", marginBottom: "var(--space-5)" }}>
          <Card>
            <h3 style={sectionTitle}>Spend lifecycle</h3>
            <p style={sectionSub}>Requisition → committed PO → realized spend, with the leakage that escapes management at each step.</p>
            {funnelStages.length > 0 ? (
              <FunnelChart stages={funnelStages} formatValue={(v) => fmtUSD(v, true)} />
            ) : (
              <p style={sectionSub}>No data.</p>
            )}
          </Card>

          <Card>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "var(--space-3)" }}>
              <div>
                <h3 style={sectionTitle}>Spend trend</h3>
                <p style={sectionSub}>Paid spend over time with the managed-spend overlay. Hover for exact values.</p>
              </div>
              <SegSelect options={GRAIN_OPTIONS} value={grain} onChange={(v) => setGrain(v as TrendGrain)} />
            </div>
            {trendPoints.length > 0 ? (
              <SpendTrendChart points={trendPoints} width={760} height={300} />
            ) : (
              <p style={sectionSub}>No data.</p>
            )}
          </Card>
        </div>

        {/* Composition + managed-status quadrant */}
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-5)", marginBottom: "var(--space-5)" }}>
          <Card>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: "var(--space-3)" }}>
              <div>
                <h3 style={sectionTitle}>Spend composition</h3>
                <p style={sectionSub}>Managed (filled) vs unmanaged tail. Click a bar to drill into its top suppliers.</p>
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
                width={620}
                height={Math.max(200, compositionBars.length * 30 + 24)}
                onBarClick={toggleDrill}
                activeLabel={drill?.value ?? null}
              />
            ) : (
              <p style={sectionSub}>No data.</p>
            )}
          </Card>

          <Card>
            <h3 style={sectionTitle}>Supplier Pareto</h3>
            <p style={sectionSub}>Spend concentration — how few suppliers carry the book. The 80% cumulative line is the tail-rationalization cut.</p>
            {concentration.length > 0 ? (
              <ParetoChart
                data={concentration.slice(0, 12).map((r) => ({
                  label: r.supplier_name ?? r.supplier_id,
                  spend: num(r.trailing_spend),
                  cumulative: num(r.cumulative_pct),
                }))}
                width={620}
                height={300}
                formatValue={(v) => fmtUSD(v, true)}
                onBarClick={(i) => launchSupplier(concentration[i].supplier_id)}
              />
            ) : (
              <p style={sectionSub}>No data.</p>
            )}
          </Card>
        </div>

        {/* Drill: top suppliers within the clicked composition slice */}
        {drill && (
          <Card style={{ marginBottom: "var(--space-5)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "var(--space-3)" }}>
              <h3 style={{ ...sectionTitle, marginBottom: 0 }}>
                Top suppliers — <span style={{ color: "var(--db-lava-600)" }}>{slice2title(drill.value)}</span>
              </h3>
              <button
                onClick={() => setDrill(null)}
                style={{ background: "transparent", border: "1px solid var(--border-strong)", borderRadius: "var(--radius-sm)", color: "var(--fg-2)", fontFamily: "var(--font-mono)", fontSize: "var(--fs-caption)", padding: "2px 10px", cursor: "pointer" }}
              >
                clear ✕
              </button>
            </div>
            {drillLoading ? (
              <p style={sectionSub}>Loading…</p>
            ) : drillRows.length > 0 ? (
              <div style={{ overflowX: "auto" }}>
                <table style={{ borderCollapse: "collapse", minWidth: "100%" }}>
                  <thead>
                    <tr>
                      <th style={th}>Supplier</th>
                      <th style={{ ...th, textAlign: "right" }}>Spend</th>
                      <th style={{ ...th, textAlign: "right" }}>Managed $</th>
                      <th style={{ ...th, textAlign: "right" }}>Managed %</th>
                      <th style={th}></th>
                    </tr>
                  </thead>
                  <tbody>
                    {drillRows.map((r) => (
                      <tr
                        key={r.supplier_id}
                        onClick={() => launchSupplier(r.supplier_id)}
                        onMouseEnter={() => setHoverRow(r.supplier_id)}
                        onMouseLeave={() => setHoverRow(null)}
                        style={{ cursor: "pointer", background: hoverRow === r.supplier_id ? "var(--bg-subtle)" : undefined }}
                      >
                        <td style={td}>{r.supplier_name ?? r.supplier_id}</td>
                        <td style={tdNum}>{fmtUSD(num(r.total_spend), true)}</td>
                        <td style={tdNum}>{fmtUSD(num(r.managed_spend), true)}</td>
                        <td style={tdNum}>{fmtPct(r.managed_pct)}</td>
                        <td style={{ ...td, textAlign: "right", color: "var(--db-lava-600)" }}>open →</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <p style={sectionSub}>No suppliers in this slice for the selected window.</p>
            )}
          </Card>
        )}

        {/* Action list: highest-leverage suppliers */}
        <Card>
          <h3 style={sectionTitle}>Highest-leverage suppliers</h3>
          <p style={sectionSub}>
            Top 20 by spend in the window. The action targets are large suppliers with low managed % or high maverick % — concentration with leakage.
            Click a row to open the supplier's scorecard.
          </p>
          <div style={{ overflowX: "auto" }}>
            <table style={{ borderCollapse: "collapse", minWidth: "100%" }}>
              <thead>
                <tr>
                  <th style={th}>#</th>
                  <th style={th}>Supplier</th>
                  <th style={{ ...th, textAlign: "right" }}>Spend</th>
                  <th style={{ ...th, textAlign: "right" }}>Cumulative %</th>
                  <th style={{ ...th, textAlign: "right" }}>Managed %</th>
                  <th style={{ ...th, textAlign: "right" }}>Maverick %</th>
                  <th style={{ ...th, textAlign: "right" }}>Avg DPO</th>
                  <th style={th}></th>
                </tr>
              </thead>
              <tbody>
                {concentration.map((r, i) => {
                  const mgPct = r.managed_spend_pct == null ? null : num(r.managed_spend_pct);
                  const mvPct = r.measured_maverick_pct == null ? null : num(r.measured_maverick_pct);
                  const isLever = (mgPct != null && mgPct < 50) || (mvPct != null && mvPct > 25);
                  return (
                    <tr
                      key={r.supplier_id}
                      onClick={() => launchSupplier(r.supplier_id)}
                      onMouseEnter={() => setHoverRow(r.supplier_id)}
                      onMouseLeave={() => setHoverRow(null)}
                      style={{ cursor: "pointer", background: hoverRow === r.supplier_id ? "var(--bg-subtle)" : undefined }}
                    >
                      <td style={{ ...tdNum, color: "var(--fg-3)" }}>{i + 1}</td>
                      <td style={td}>{r.supplier_name ?? r.supplier_id}</td>
                      <td style={tdNum}>{fmtUSD(num(r.trailing_spend), true)}</td>
                      <td style={tdNum}>{fmtPct(r.cumulative_pct)}</td>
                      <td style={{ ...tdNum, color: mgPct != null && mgPct < 50 ? "var(--db-lava-600)" : undefined }}>{fmtPct(mgPct)}</td>
                      <td style={{ ...tdNum, color: mvPct != null && mvPct > 25 ? "var(--db-lava-600)" : undefined }}>{fmtPct(mvPct)}</td>
                      <td style={tdNum}>{fmtDays(r.avg_dpo)}</td>
                      <td style={{ ...td, textAlign: "right" }}>
                        {isLever && (
                          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, fontWeight: 600, color: "var(--db-lava-600)", border: "1px solid var(--db-lava-600)", borderRadius: "var(--radius-pill)", padding: "1px 8px" }}>
                            LEVER
                          </span>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {concentration.length === 0 && (
                  <tr><td style={td} colSpan={8}>No data.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  );
}
