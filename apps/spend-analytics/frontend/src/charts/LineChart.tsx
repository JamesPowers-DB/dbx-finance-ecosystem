import React, { useMemo } from "react";
import { scaleLinear } from "d3-scale";
import { line, area, curveMonotoneX } from "d3-shape";

export interface LinePoint {
  label: string;
  value: number;
}

interface LineChartProps {
  points: LinePoint[];
  width?: number;
  height?: number;
  color?: string;
  formatValue?: (v: number) => string;
}

/**
 * Single-series line chart with a left $ y-axis and x labels — for the supplier
 * spend-over-time view (where the axis-less sparkline didn't denote scale).
 */
export function LineChart({
  points,
  width = 480,
  height = 170,
  color = "var(--db-lava-600)",
  formatValue = (v) => (v >= 1e9 ? `$${(v / 1e9).toFixed(1)}B` : v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `$${(v / 1e3).toFixed(0)}k` : `$${v}`),
}: LineChartProps) {
  const margin = { top: 12, right: 16, bottom: 28, left: 52 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const maxV = useMemo(() => Math.max(...points.map((p) => p.value), 1) * 1.1, [points]);
  const x = useMemo(() => scaleLinear().domain([0, Math.max(points.length - 1, 1)]).range([0, innerW]), [points.length, innerW]);
  const y = useMemo(() => scaleLinear().domain([0, maxV]).range([innerH, 0]), [maxV, innerH]);

  const linePath = useMemo(() => line<LinePoint>().x((_, i) => x(i)).y((p) => y(p.value)).curve(curveMonotoneX)(points) ?? "", [points, x, y]);
  const areaPath = useMemo(
    () => area<LinePoint>().x((_, i) => x(i)).y0(innerH).y1((p) => y(p.value)).curve(curveMonotoneX)(points) ?? "",
    [points, x, y, innerH],
  );

  if (points.length < 2) return null;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img" style={{ width: "100%", height: "auto" }}>
      <defs>
        <linearGradient id="line-area-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.16} />
          <stop offset="100%" stopColor={color} stopOpacity={0.01} />
        </linearGradient>
      </defs>
      <g transform={`translate(${margin.left},${margin.top})`}>
        {y.ticks(4).map((t) => (
          <g key={t} transform={`translate(0,${y(t)})`}>
            <line x1={0} x2={innerW} stroke="var(--db-gray-lines)" strokeWidth={0.5} />
            <text x={-8} textAnchor="end" dominantBaseline="middle" fontFamily="var(--font-mono)" fontSize={10} fill="var(--fg-3)">{formatValue(t)}</text>
          </g>
        ))}
        <path d={areaPath} fill="url(#line-area-fill)" />
        <path d={linePath} fill="none" stroke={color} strokeWidth={2} />
        {points.map((p, i) => (
          <g key={i}>
            <circle cx={x(i)} cy={y(p.value)} r={2.5} fill={color} />
            <text x={x(i)} y={innerH + 18} textAnchor="middle" fontFamily="var(--font-mono)" fontSize={9.5} fill="var(--fg-3)">{p.label}</text>
          </g>
        ))}
      </g>
    </svg>
  );
}
