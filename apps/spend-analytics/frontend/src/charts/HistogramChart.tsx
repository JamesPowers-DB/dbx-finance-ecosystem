import React, { useMemo } from "react";
import { scaleLinear, scaleBand } from "d3-scale";

interface HistogramBucket {
  bucket: string;
  count: number;
}

interface HistogramChartProps {
  data: HistogramBucket[];
  width?: number;
  height?: number;
  color?: string;
  referenceAt?: number;
}

export function HistogramChart({
  data,
  width = 480,
  height = 160,
  color = "var(--db-navy-800)",
  referenceAt = 0.75,
}: HistogramChartProps) {
  const margin = { top: 12, right: 16, bottom: 28, left: 48 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const maxCount = useMemo(() => Math.max(...data.map((d) => d.count), 1), [data]);
  const y = useMemo(() => scaleLinear().domain([0, maxCount]).range([innerH, 0]), [maxCount, innerH]);

  const xBand = useMemo(
    () =>
      scaleBand()
        .domain(data.map((d) => d.bucket))
        .range([0, innerW])
        .padding(0.1),
    [data, innerW],
  );

  const refX = referenceAt * innerW;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img" style={{ width: "100%", height: "auto" }}>
      <g transform={`translate(${margin.left},${margin.top})`}>
        {/* Y axis */}
        {y.ticks(4).map((t) => (
          <g key={t} transform={`translate(0,${y(t)})`}>
            <line x1={0} x2={innerW} stroke="var(--db-gray-lines)" strokeWidth={0.5} />
            <text x={-6} textAnchor="end" dominantBaseline="middle"
              fontFamily="var(--font-mono)" fontSize={10} fill="var(--fg-3)">
              {t.toLocaleString()}
            </text>
          </g>
        ))}

        {/* Reference line at confidence threshold */}
        <line
          x1={refX} x2={refX}
          y1={-4} y2={innerH}
          stroke="var(--db-lava-600)"
          strokeWidth={1.5}
          strokeDasharray="3 3"
        />
        <text
          x={refX + 3}
          y={4}
          fontFamily="var(--font-mono)"
          fontSize={9}
          fill="var(--db-lava-600)"
        >
          0.75
        </text>

        {/* Bars */}
        {data.map((d) => {
          const bx = xBand(d.bucket) ?? 0;
          const bw = xBand.bandwidth();
          const by = y(d.count);
          const bh = innerH - by;
          return (
            <g key={d.bucket}>
              <rect x={bx} y={by} width={bw} height={bh} rx={2} fill={color} opacity={0.75} />
            </g>
          );
        })}

        {/* X labels — show first, middle, last */}
        {data.map((d, i) => {
          if (i !== 0 && i !== Math.floor(data.length / 2) && i !== data.length - 1) return null;
          return (
            <text
              key={d.bucket}
              x={(xBand(d.bucket) ?? 0) + xBand.bandwidth() / 2}
              y={innerH + 16}
              textAnchor="middle"
              fontFamily="var(--font-mono)"
              fontSize={9}
              fill="var(--fg-3)"
            >
              {d.bucket.split("–")[0]}
            </text>
          );
        })}
      </g>
    </svg>
  );
}
