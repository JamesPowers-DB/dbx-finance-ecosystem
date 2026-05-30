import React, { useMemo } from "react";
import { scaleLinear } from "d3-scale";
import { line, area, curveMonotoneX } from "d3-shape";

export interface SpendTrendPoint {
  period: string;
  total_spend: number;
  managed_spend: number;
}

interface SpendTrendChartProps {
  points: SpendTrendPoint[];
  width?: number;
  height?: number;
}

/**
 * Period-x-axis trend: total paid spend (navy) with managed spend (lava, filled)
 * overlaid. Non-cumulative — each point is that quarter's spend. Modeled on
 * BurnDownChart's d3-shape approach so it matches the hand-drawn chart style.
 */
export function SpendTrendChart({ points, width = 720, height = 260 }: SpendTrendChartProps) {
  const margin = { top: 20, right: 24, bottom: 36, left: 64 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const data = useMemo(() => points, [points]);
  const maxY = useMemo(
    () => Math.max(...data.map((d) => d.total_spend), 1) * 1.1,
    [data],
  );

  const x = useMemo(
    () => scaleLinear().domain([0, Math.max(data.length - 1, 1)]).range([0, innerW]),
    [data.length, innerW],
  );
  const y = useMemo(() => scaleLinear().domain([0, maxY]).range([innerH, 0]), [maxY, innerH]);

  const mkLine = (key: "total_spend" | "managed_spend") =>
    line<SpendTrendPoint>().x((_, i) => x(i)).y((d) => y(d[key])).curve(curveMonotoneX)(data) ?? "";
  const totalLine = useMemo(() => mkLine("total_spend"), [data, x, y]);
  const managedLine = useMemo(() => mkLine("managed_spend"), [data, x, y]);
  const managedArea = useMemo(
    () =>
      area<SpendTrendPoint>()
        .x((_, i) => x(i))
        .y0(innerH)
        .y1((d) => y(d.managed_spend))
        .curve(curveMonotoneX)(data) ?? "",
    [data, x, y, innerH],
  );

  const fmtUSD = (v: number) =>
    v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : v >= 1e6 ? `$${(v / 1e6).toFixed(0)}M` : `$${v}`;
  const yTicks = useMemo(() => y.ticks(5), [y]);
  const showLabels = data.length <= 16;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img" style={{ width: "100%", height: "auto" }}>
      <defs>
        <linearGradient id="trend-managed-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--db-lava-600)" stopOpacity={0.18} />
          <stop offset="100%" stopColor="var(--db-lava-600)" stopOpacity={0.01} />
        </linearGradient>
      </defs>

      {/* Legend */}
      <g>
        <rect x={margin.left} y={4} width={12} height={8} rx={2} fill="var(--db-navy-400)" />
        <text x={margin.left + 16} y={11} fontFamily="var(--font-mono)" fontSize={10} fill="var(--fg-2)">Total spend</text>
        <rect x={margin.left + 92} y={4} width={12} height={8} rx={2} fill="var(--db-lava-600)" />
        <text x={margin.left + 108} y={11} fontFamily="var(--font-mono)" fontSize={10} fill="var(--fg-2)">Managed</text>
      </g>

      <g transform={`translate(${margin.left},${margin.top})`}>
        {yTicks.map((t) => (
          <g key={t} transform={`translate(0,${y(t)})`}>
            <line x1={0} x2={innerW} stroke="var(--db-gray-lines)" strokeWidth={0.5} />
            <text x={-8} textAnchor="end" fontFamily="var(--font-mono)" fontSize={11} fill="var(--fg-3)" dominantBaseline="middle">
              {fmtUSD(t)}
            </text>
          </g>
        ))}

        <path d={managedArea} fill="url(#trend-managed-area)" />
        <path d={totalLine} fill="none" stroke="var(--db-navy-400)" strokeWidth={2} />
        <path d={managedLine} fill="none" stroke="var(--db-lava-600)" strokeWidth={2} />

        {data.map((d, i) => (
          <g key={i}>
            <circle cx={x(i)} cy={y(d.total_spend)} r={2.5} fill="var(--db-navy-400)" />
            <circle cx={x(i)} cy={y(d.managed_spend)} r={2.5} fill="var(--db-lava-600)" />
            {showLabels && (
              <text
                x={x(i)}
                y={innerH + 20}
                textAnchor="middle"
                fontFamily="var(--font-mono)"
                fontSize={9}
                fill="var(--fg-3)"
              >
                {d.period}
              </text>
            )}
          </g>
        ))}
      </g>
    </svg>
  );
}
