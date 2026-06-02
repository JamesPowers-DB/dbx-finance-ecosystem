import React, { useMemo } from "react";
import { scaleLinear, scaleBand } from "d3-scale";

interface BarChartRow {
  label: string;
  value: number;
  value2?: number; // optional stacked second bar
}

interface BarChartProps {
  data: BarChartRow[];
  width?: number;
  height?: number;
  color?: string;
  color2?: string;
  formatValue?: (v: number) => string;
  label2?: string;
  label1?: string;
  /** When set, bars become clickable and report their label. */
  onBarClick?: (label: string) => void;
  /** When set, the matching bar stays full-opacity and the rest dim. */
  activeLabel?: string | null;
}

export function BarChart({
  data,
  width = 640,
  height = 320,
  color = "var(--db-lava-600)",
  color2 = "var(--db-navy-400)",
  formatValue = (v) => `$${(v / 1e6).toFixed(2)}M`,
  label1,
  label2,
  onBarClick,
  activeLabel,
}: BarChartProps) {
  const margin = { top: 12, right: 48, bottom: 24, left: 100 };
  const innerW = width - margin.left - margin.right;
  const innerH = height - margin.top - margin.bottom;

  const maxVal = useMemo(
    () => Math.max(...data.map((d) => (d.value2 ? d.value + d.value2 : d.value)), 1),
    [data],
  );

  const x = useMemo(() => scaleLinear().domain([0, maxVal]).range([0, innerW]), [maxVal, innerW]);
  const yBand = useMemo(
    () =>
      scaleBand()
        .domain(data.map((d) => d.label))
        .range([0, innerH])
        .padding(0.28),
    [data, innerH],
  );

  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img" style={{ width: "100%", height: "auto" }}>
      {label1 && (
        <g>
          <rect x={margin.left} y={4} width={12} height={8} rx={2} fill={color} />
          <text x={margin.left + 16} y={11} fontFamily="var(--font-mono)" fontSize={10} fill="var(--fg-2)">{label1}</text>
          {label2 && (
            <>
              <rect x={margin.left + 80} y={4} width={12} height={8} rx={2} fill={color2} />
              <text x={margin.left + 96} y={11} fontFamily="var(--font-mono)" fontSize={10} fill="var(--fg-2)">{label2}</text>
            </>
          )}
        </g>
      )}
      <g transform={`translate(${margin.left},${margin.top})`}>
        {/* Base line */}
        <line x1={0} x2={0} y1={0} y2={innerH} stroke="var(--border)" />
        {data.map((d) => {
          const cy = yBand(d.label) ?? 0;
          const bh = yBand.bandwidth();
          // Give any non-zero value at least a 2px sliver so tiny bars next to a
          // dominant one don't vanish entirely.
          const w1 = d.value > 0 ? Math.max(x(d.value), 2) : 0;
          const w2 = d.value2 && d.value2 > 0 ? Math.max(x(d.value2), 2) : 0;
          const dim = activeLabel && d.label !== activeLabel ? 0.32 : 1;
          const isActive = activeLabel === d.label;
          const barEnd = w1 + w2;
          const valLabel = formatValue(d.value + (d.value2 ?? 0));
          // If the value label would overflow the right edge, render it inside the
          // bar end (right-aligned, light) instead of clipping it (the "$2" bug).
          const labelInside = barEnd + valLabel.length * 6.2 + 6 > innerW;
          return (
            <g
              key={d.label}
              onClick={onBarClick ? () => onBarClick(d.label) : undefined}
              style={{ cursor: onBarClick ? "pointer" : "default" }}
            >
              {/* full-width hit area so the whole row is clickable */}
              {onBarClick && <rect x={0} y={cy} width={innerW} height={bh} fill="transparent" />}
              <rect x={0} y={cy} width={w1} height={bh} rx={2} fill={color} opacity={0.85 * dim} />
              {d.value2 && (
                <rect x={w1} y={cy} width={w2} height={bh} rx={2} fill={color2} opacity={0.7 * dim} />
              )}
              {isActive && (
                <rect x={0} y={cy} width={Math.max(w1 + w2, 2)} height={bh} rx={2} fill="none" stroke="var(--db-lava-600)" strokeWidth={1.5} />
              )}
              <text
                x={-6}
                y={cy + bh / 2}
                textAnchor="end"
                dominantBaseline="middle"
                fontFamily="var(--font-mono)"
                fontSize={11}
                fill="var(--fg-2)"
              >
                {d.label.length > 14 ? d.label.slice(0, 13) + "…" : d.label}
              </text>
              <text
                x={labelInside ? barEnd - 6 : barEnd + 4}
                y={cy + bh / 2}
                textAnchor={labelInside ? "end" : "start"}
                dominantBaseline="middle"
                fontFamily="var(--font-mono)"
                fontSize={11}
                fill={labelInside ? "var(--fg-on-dark)" : "var(--fg-2)"}
              >
                {valLabel}
              </text>
            </g>
          );
        })}
      </g>
    </svg>
  );
}
