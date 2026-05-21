import React, { useMemo } from "react";
import { scaleLinear } from "d3-scale";
import { line, area, curveMonotoneX } from "d3-shape";
import type { BurnDownPoint } from "../types";

interface BurnDownChartProps {
  points: BurnDownPoint[];
  committedSpend?: number;
  width?: number;
  height?: number;
}

export function BurnDownChart({
  points,
  committedSpend,
  width = 640,
  height = 220,
}: BurnDownChartProps) {
  const margin = { top: 20, right: 24, bottom: 36, left: 64 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const data = useMemo(() => points, [points]);

  const maxY = useMemo(() => {
    const dataMax = Math.max(...data.map((d) => d.cumulative_spend), 0);
    return committedSpend ? Math.max(committedSpend, dataMax) * 1.05 : dataMax * 1.1;
  }, [data, committedSpend]);

  const x = useMemo(
    () => scaleLinear().domain([0, Math.max(data.length - 1, 1)]).range([0, innerW]),
    [data.length, innerW],
  );
  const y = useMemo(
    () => scaleLinear().domain([0, maxY]).range([innerH, 0]),
    [maxY, innerH],
  );

  const linePath = useMemo(
    () =>
      line<BurnDownPoint>()
        .x((_, i) => x(i))
        .y((d) => y(d.cumulative_spend))
        .curve(curveMonotoneX)(data) ?? "",
    [data, x, y],
  );
  const areaPath = useMemo(
    () =>
      area<BurnDownPoint>()
        .x((_, i) => x(i))
        .y0(innerH)
        .y1((d) => y(d.cumulative_spend))
        .curve(curveMonotoneX)(data) ?? "",
    [data, x, y, innerH],
  );

  const fmtUSD = (v: number) =>
    v >= 1e6 ? `$${(v / 1e6).toFixed(1)}M` : v >= 1e3 ? `$${(v / 1e3).toFixed(0)}K` : `$${v}`;

  const yTicks = useMemo(() => y.ticks(5), [y]);
  const showLabels = data.length <= 12;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img" style={{ width: "100%", height: "auto" }}>
      <defs>
        <linearGradient id="burndown-area" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="var(--db-lava-600)" stopOpacity={0.18} />
          <stop offset="100%" stopColor="var(--db-lava-600)" stopOpacity={0.01} />
        </linearGradient>
      </defs>
      <g transform={`translate(${margin.left},${margin.top})`}>
        {/* Y grid + ticks */}
        {yTicks.map((t) => (
          <g key={t} transform={`translate(0,${y(t)})`}>
            <line x1={0} x2={innerW} stroke="var(--db-gray-lines)" strokeWidth={0.5} />
            <text
              x={-8}
              textAnchor="end"
              fontFamily="var(--font-mono)"
              fontSize={11}
              fill="var(--fg-3)"
              dominantBaseline="middle"
            >
              {fmtUSD(t)}
            </text>
          </g>
        ))}

        {/* Committed-spend reference line */}
        {committedSpend && (
          <>
            <line
              x1={0} x2={innerW}
              y1={y(committedSpend)} y2={y(committedSpend)}
              stroke="var(--db-lava-600)"
              strokeWidth={1.5}
              strokeDasharray="4 3"
            />
            <text
              x={innerW + 4}
              y={y(committedSpend)}
              fontFamily="var(--font-mono)"
              fontSize={10}
              fill="var(--db-lava-600)"
              dominantBaseline="middle"
            >
              Budget
            </text>
          </>
        )}

        {/* Area fill */}
        <path d={areaPath} fill="url(#burndown-area)" />

        {/* Line */}
        <path d={linePath} fill="none" stroke="var(--db-lava-600)" strokeWidth={2} />

        {/* X axis labels */}
        {data.map((d, i) => (
          showLabels && (
            <text
              key={i}
              x={x(i)}
              y={innerH + 20}
              textAnchor="middle"
              fontFamily="var(--font-mono)"
              fontSize={10}
              fill="var(--fg-3)"
            >
              {d.period}
            </text>
          )
        ))}

        {/* Dots */}
        {data.map((d, i) => (
          <circle
            key={i}
            cx={x(i)}
            cy={y(d.cumulative_spend)}
            r={3}
            fill="var(--db-lava-600)"
          />
        ))}
      </g>
    </svg>
  );
}
