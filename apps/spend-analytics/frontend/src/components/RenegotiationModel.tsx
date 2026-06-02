import React, { useMemo, useState } from "react";
import { scaleLinear } from "d3-scale";
import { line, curveMonotoneX } from "d3-shape";
import { fmtUSD, fmtPct } from "../format";
import type { SupplierEconomics } from "../types";

/**
 * Client-side renegotiation what-if. Three levers — no DB writeback, purely an
 * interactive projection over the supplier's governed T12M economics:
 *   1. Extend payment terms  → one-time working capital freed
 *   2. Renew / renegotiate    → % discount on addressable spend (annual savings)
 *   3. Get spend under mgmt   → capture % of the unmanaged tail at a savings rate
 * The assumptions are deliberately simple and shown inline so the demo can
 * defend every number. The forecast chart shows the next 12 monthly run-rates,
 * with discount + under-management savings phasing in over the year so the
 * scenario lines fan away from the flat baseline as the sliders move.
 */

const num = (v: unknown): number => {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
};

// Assumed savings realized on tail spend once it's competitively sourced /
// put on contract. Shown to the user as a note, fixed here for clarity.
const MANAGED_SAVINGS_RATE = 0.08;
const MONTHS = 12;

function parseTermsDays(terms: string | null | undefined): number {
  if (!terms) return 30;
  const m = /(\d+)/.exec(terms);
  return m ? Number(m[1]) : 30;
}

const labelStyle: React.CSSProperties = {
  fontFamily: "var(--font-mono)",
  fontSize: 13,
  color: "var(--fg-2)",
  display: "flex",
  justifyContent: "space-between",
  alignItems: "baseline",
  marginBottom: 4,
};
const resultStyle: React.CSSProperties = {
  fontFamily: "var(--font-mono)",
  fontSize: 13,
  fontWeight: 700,
  color: "var(--db-lava-600)",
};

function Lever({
  title, hint, min, max, step, value, suffix, onChange, result,
}: {
  title: string; hint: string; min: number; max: number; step: number;
  value: number; suffix: string; onChange: (v: number) => void; result: string;
}) {
  return (
    <div style={{ marginBottom: "var(--space-4)" }}>
      <div style={labelStyle}>
        <span>{title}: <strong style={{ color: "var(--fg-1)" }}>{value}{suffix}</strong></span>
        <span style={resultStyle}>{result}</span>
      </div>
      <input
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        style={{ width: "100%", accentColor: "var(--db-lava-600)", cursor: "pointer" }}
      />
      <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--fg-3)", marginTop: 2 }}>{hint}</div>
    </div>
  );
}

interface MonthRow { month: number; baseline: number; discount: number; full: number; }

function ForecastChart({ months, formatValue }: { months: MonthRow[]; formatValue: (v: number) => string }) {
  const width = 380;
  const height = 210;
  const margin = { top: 28, right: 12, bottom: 24, left: 52 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const baseline = months[0]?.baseline ?? 1;
  const lo = Math.min(...months.map((m) => m.full));
  // Zoomed (non-zero) y-axis so the savings fan is legible — savings are a small
  // share of run-rate, and a zero-based axis would flatten the lines together.
  const yMin = Math.max(0, lo * 0.8);
  const yMax = baseline * 1.04;

  const x = scaleLinear().domain([1, MONTHS]).range([0, innerW]);
  const y = scaleLinear().domain([yMin, yMax]).range([innerH, 0]);
  const mk = (key: "baseline" | "discount" | "full") =>
    line<MonthRow>().x((d) => x(d.month)).y((d) => y(d[key])).curve(curveMonotoneX)(months) ?? "";

  const legend = [
    { label: "Baseline", color: "var(--fg-3)" },
    { label: "+ discount", color: "var(--db-navy-800)" },
    { label: "+ under-mgmt", color: "var(--db-lava-600)" },
  ];

  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img" style={{ width: "100%", height: "auto" }}>
      {/* legend */}
      <g>
        {legend.map((l, i) => (
          <g key={l.label} transform={`translate(${margin.left + i * 110},10)`}>
            <rect x={0} y={0} width={11} height={4} rx={1} fill={l.color} />
            <text x={15} y={5} fontFamily="var(--font-mono)" fontSize={11} fill="var(--fg-2)">{l.label}</text>
          </g>
        ))}
      </g>
      <g transform={`translate(${margin.left},${margin.top})`}>
        {y.ticks(4).map((t) => (
          <g key={t} transform={`translate(0,${y(t)})`}>
            <line x1={0} x2={innerW} stroke="var(--db-gray-lines)" strokeWidth={0.5} />
            <text x={-8} textAnchor="end" dominantBaseline="middle" fontFamily="var(--font-mono)" fontSize={11} fill="var(--fg-3)">{formatValue(t)}</text>
          </g>
        ))}
        <path d={mk("baseline")} fill="none" stroke="var(--fg-3)" strokeWidth={1.5} strokeDasharray="4 3" />
        <path d={mk("discount")} fill="none" stroke="var(--db-navy-800)" strokeWidth={2} />
        <path d={mk("full")} fill="none" stroke="var(--db-lava-600)" strokeWidth={2} />
        {[1, 4, 8, 12].map((mo) => (
          <text key={mo} x={x(mo)} y={innerH + 16} textAnchor="middle" fontFamily="var(--font-mono)" fontSize={10} fill="var(--fg-3)">M{mo}</text>
        ))}
      </g>
    </svg>
  );
}

export function RenegotiationModel({
  economics,
  avgDpo,
  paymentTerms,
}: {
  economics: Partial<SupplierEconomics>;
  avgDpo: number | null;
  paymentTerms: string | null;
}) {
  const spend = num(economics.paid_spend);
  const addressable = num(economics.addressable_spend);
  const unmanaged = num(economics.unmanaged_spend);
  const baselineDpo = avgDpo != null && Number.isFinite(Number(avgDpo)) ? Number(avgDpo) : parseTermsDays(paymentTerms);

  const termsFloor = Math.max(15, Math.round(baselineDpo));
  const [targetDays, setTargetDays] = useState<number>(Math.min(60, 90 < termsFloor ? termsFloor : Math.max(60, termsFloor)));
  const [discountPct, setDiscountPct] = useState<number>(6);
  const [capturePct, setCapturePct] = useState<number>(60);

  const m = useMemo(() => {
    const workingCapital = (spend / 365) * Math.max(0, targetDays - baselineDpo);
    const contractSavings = addressable * (discountPct / 100);
    const underMgmtSavings = unmanaged * (capturePct / 100) * MANAGED_SAVINGS_RATE;
    const annualSavings = contractSavings + underMgmtSavings;

    // Forward 12-month run-rates. Savings phase in linearly across the year so
    // the scenario lines diverge from the flat baseline.
    const baseM = spend / 12;
    const steadyDiscount = Math.max(0, (spend - contractSavings) / 12);
    const steadyFull = Math.max(0, (spend - annualSavings) / 12);
    const months: MonthRow[] = Array.from({ length: MONTHS }, (_, i) => {
      const f = i / (MONTHS - 1);
      return {
        month: i + 1,
        baseline: baseM,
        discount: baseM - (baseM - steadyDiscount) * f,
        full: baseM - (baseM - steadyFull) * f,
      };
    });

    return {
      workingCapital,
      contractSavings,
      underMgmtSavings,
      annualSavings,
      projectedSpend: Math.max(0, spend - annualSavings),
      months,
    };
  }, [spend, addressable, unmanaged, baselineDpo, targetDays, discountPct, capturePct]);

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginBottom: "var(--space-3)" }}>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.06em" }}>
          Renegotiation what-if
        </div>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--fg-3)" }}>model only · nothing saved</span>
      </div>

      {/* 40% levers · 24% projection stats · 36% forecast chart */}
      <div style={{ display: "grid", gridTemplateColumns: "minmax(0, 40fr) minmax(0, 24fr) minmax(0, 36fr)", gap: "var(--space-5)", alignItems: "start" }}>
        <div>
          <Lever
            title="Extend payment terms to"
            hint={`vs ~${baselineDpo.toFixed(0)}d realized today · frees daily-spend × Δdays of cash`}
            min={termsFloor}
            max={90}
            step={5}
            value={targetDays}
            suffix="d"
            onChange={setTargetDays}
            result={`${fmtUSD(m.workingCapital, true)} working capital`}
          />
          <Lever
            title="Renew / renegotiate — discount"
            hint="applied to addressable spend as an annual unit-price reduction"
            min={0}
            max={15}
            step={1}
            value={discountPct}
            suffix="%"
            onChange={setDiscountPct}
            result={`${fmtUSD(m.contractSavings, true)} / yr`}
          />
          <Lever
            title="Capture unmanaged tail"
            hint={`bring off-contract spend under management · assumes ${(MANAGED_SAVINGS_RATE * 100).toFixed(0)}% sourcing savings`}
            min={0}
            max={100}
            step={5}
            value={capturePct}
            suffix="%"
            onChange={setCapturePct}
            result={`${fmtUSD(m.underMgmtSavings, true)} / yr`}
          />
        </div>

        {/* Projection summary */}
        <div style={{ background: "var(--bg-canvas)", border: "1px solid var(--border)", borderRadius: "var(--radius-md)", padding: "var(--space-4)" }}>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "var(--space-2)" }}>
            Projected next 12 months
          </div>
          <div style={{ fontSize: "var(--fs-h3)", fontFamily: "var(--font-display)", fontWeight: 700, color: "var(--fg-1)", letterSpacing: "var(--tracking-tight)" }}>
            {fmtUSD(m.projectedSpend, true)}
          </div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--db-green-700)", marginBottom: "var(--space-3)" }}>
            −{fmtUSD(m.annualSavings, true)} vs {fmtUSD(spend, true)} today
          </div>
          <Row label="Annual savings" value={fmtUSD(m.annualSavings, true)} strong />
          <Row label="· from discount" value={fmtUSD(m.contractSavings, true)} />
          <Row label="· from under-mgmt" value={fmtUSD(m.underMgmtSavings, true)} />
          <div style={{ height: 1, background: "var(--border)", margin: "var(--space-2) 0" }} />
          <Row label="One-time working capital" value={fmtUSD(m.workingCapital, true)} />
          <Row label="Effective savings rate" value={fmtPct(spend > 0 ? (m.annualSavings / spend) * 100 : 0)} />
        </div>

        {/* Forecast chart */}
        <div>
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--fg-3)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "var(--space-2)" }}>
            Monthly spend run-rate
          </div>
          <ForecastChart months={m.months} formatValue={(v) => fmtUSD(v, true)} />
        </div>
      </div>
    </div>
  );
}

function Row({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--font-mono)", fontSize: 12, padding: "3px 0", color: strong ? "var(--fg-1)" : "var(--fg-2)", fontWeight: strong ? 700 : 400 }}>
      <span>{label}</span>
      <span>{value}</span>
    </div>
  );
}
