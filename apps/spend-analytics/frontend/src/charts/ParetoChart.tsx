import React, { useMemo } from "react";
import { scaleLinear, scaleBand } from "d3-scale";
import { line, curveMonotoneX } from "d3-shape";

export interface ParetoRow {
  label: string;
  spend: number;
  cumulative: number; // 0–100
}

interface ParetoChartProps {
  data: ParetoRow[];
  width?: number;
  height?: number;
  formatValue?: (v: number) => string;
  onBarClick?: (index: number) => void;
}

/**
 * Classic Pareto: descending spend bars (left $ axis) with a cumulative-share
 * line (right % axis) and an 80% reference line — the tail-rationalization cut.
 */
export function ParetoChart({
  data,
  width = 620,
  height = 300,
  formatValue = (v) => `$${(v / 1e6).toFixed(0)}M`,
  onBarClick,
}: ParetoChartProps) {
  const margin = { top: 16, right: 44, bottom: 72, left: 56 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const maxSpend = useMemo(() => Math.max(...data.map((d) => d.spend), 1), [data]);
  const xBand = useMemo(
    () => scaleBand<number>().domain(data.map((_, i) => i)).range([0, innerW]).padding(0.3),
    [data, innerW],
  );
  const yL = useMemo(() => scaleLinear().domain([0, maxSpend * 1.05]).range([innerH, 0]), [maxSpend, innerH]);
  const yR = useMemo(() => scaleLinear().domain([0, 100]).range([innerH, 0]), [innerH]);

  const cx = (i: number) => (xBand(i) ?? 0) + xBand.bandwidth() / 2;
  const linePath = useMemo(
    () => line<ParetoRow>().x((_, i) => cx(i)).y((d) => yR(d.cumulative)).curve(curveMonotoneX)(data) ?? "",
    [data, xBand, yR],
  );

  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img" style={{ width: "100%", height: "auto" }}>
      <g transform={`translate(${margin.left},${margin.top})`}>
        {/* left $ axis ticks + gridlines */}
        {yL.ticks(4).map((t) => (
          <g key={t} transform={`translate(0,${yL(t)})`}>
            <line x1={0} x2={innerW} stroke="var(--db-gray-lines)" strokeWidth={0.5} />
            <text x={-8} textAnchor="end" dominantBaseline="middle" fontFamily="var(--font-mono)" fontSize={10} fill="var(--fg-3)">{formatValue(t)}</text>
          </g>
        ))}
        {/* right % axis ticks */}
        {[0, 25, 50, 75, 100].map((t) => (
          <text key={t} x={innerW + 8} y={yR(t)} dominantBaseline="middle" fontFamily="var(--font-mono)" fontSize={10} fill="var(--fg-3)">{t}%</text>
        ))}

        {/* 80% reference */}
        <line x1={0} x2={innerW} y1={yR(80)} y2={yR(80)} stroke="var(--db-lava-600)" strokeWidth={1} strokeDasharray="4 3" opacity={0.7} />
        <text x={innerW} y={yR(80) - 4} textAnchor="end" fontFamily="var(--font-mono)" fontSize={9} fill="var(--db-lava-600)">80% of spend</text>

        {/* bars */}
        {data.map((d, i) => {
          const bx = xBand(i) ?? 0;
          const bw = xBand.bandwidth();
          const top = yL(d.spend);
          const cum80 = d.cumulative <= 80;
          return (
            <g key={i} onClick={onBarClick ? () => onBarClick(i) : undefined} style={{ cursor: onBarClick ? "pointer" : "default" }}>
              <rect x={bx} y={top} width={bw} height={Math.max(innerH - top, 0)} rx={2} fill={cum80 ? "var(--db-navy-800)" : "var(--db-navy-400)"} opacity={0.9} />
              <text
                transform={`translate(${bx + bw / 2},${innerH + 8}) rotate(-40)`}
                textAnchor="end"
                fontFamily="var(--font-mono)"
                fontSize={9}
                fill="var(--fg-3)"
              >
                {d.label.length > 16 ? d.label.slice(0, 15) + "…" : d.label}
              </text>
            </g>
          );
        })}

        {/* cumulative line + dots */}
        <path d={linePath} fill="none" stroke="var(--db-lava-600)" strokeWidth={2} />
        {data.map((d, i) => (
          <circle key={i} cx={cx(i)} cy={yR(d.cumulative)} r={2.5} fill="var(--db-lava-600)" />
        ))}
      </g>
    </svg>
  );
}
