import React, { useMemo } from "react";
import { scaleLinear } from "d3-scale";
import { line, curveMonotoneX } from "d3-shape";

interface SparklineChartProps {
  values: number[];
  width?: number;
  height?: number;
  color?: string;
  showDots?: boolean;
}

export function SparklineChart({
  values,
  width = 120,
  height = 36,
  color = "var(--db-lava-600)",
  showDots = false,
}: SparklineChartProps) {
  const padding = 3;
  const innerW = width - padding * 2;
  const innerH = height - padding * 2;

  const minV = Math.min(...values);
  const maxV = Math.max(...values);
  const range = maxV - minV || 1;

  const x = useMemo(
    () => scaleLinear().domain([0, Math.max(values.length - 1, 1)]).range([0, innerW]),
    [values.length, innerW],
  );
  const y = useMemo(
    () => scaleLinear().domain([minV - range * 0.1, maxV + range * 0.1]).range([innerH, 0]),
    [minV, maxV, range, innerH],
  );

  const pathStr = useMemo(
    () =>
      line<number>()
        .x((_, i) => x(i))
        .y((v) => y(v))
        .curve(curveMonotoneX)(values) ?? "",
    [values, x, y],
  );

  if (values.length < 2) return null;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      style={{ width, height, display: "block" }}
      role="img"
    >
      <g transform={`translate(${padding},${padding})`}>
        <path d={pathStr} fill="none" stroke={color} strokeWidth={1.8} />
        {showDots &&
          values.map((v, i) => (
            <circle key={i} cx={x(i)} cy={y(v)} r={2.5} fill={color} />
          ))}
      </g>
    </svg>
  );
}
