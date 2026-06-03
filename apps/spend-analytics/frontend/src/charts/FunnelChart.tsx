import React, { useMemo } from "react";
import { scaleLinear } from "d3-scale";

export interface FunnelStage {
  stage: string;
  caption: string;
  amount: number;
  leak: number | null;
  leak_label: string | null;
}

interface FunnelChartProps {
  stages: FunnelStage[];
  width?: number;
  height?: number;
  formatValue?: (v: number) => string;
}

/**
 * Source→pay value funnel. Each stage is a left-aligned horizontal bar scaled to
 * the largest stage. The leak portion (off-contract PO $, unmanaged tail $) is
 * drawn as a warning-colored segment at the *tail* of its bar — "of this $X,
 * $Y escaped management here" — and the conversion vs the prior stage is called
 * out between bars. This is the page's action path: see where value leaks, then
 * act on the suppliers/POs below.
 */
export function FunnelChart({
  stages,
  width = 480,
  height = 416,
  formatValue = (v) => `$${(v / 1e9).toFixed(2)}B`,
}: FunnelChartProps) {
  const margin = { top: 28, right: 12, bottom: 28, left: 12 };
  const innerW = width - margin.left - margin.right;
  const rowH = (height - margin.top - margin.bottom) / Math.max(stages.length, 1);
  const barH = Math.min(44, rowH * 0.36);

  const maxAmount = useMemo(
    () => Math.max(...stages.map((s) => s.amount), 1),
    [stages],
  );
  const x = useMemo(() => scaleLinear().domain([0, maxAmount]).range([0, innerW]), [maxAmount, innerW]);

  return (
    <svg viewBox={`0 0 ${width} ${height}`} role="img" style={{ width: "100%", height: "auto" }}>
      <g transform={`translate(${margin.left},${margin.top})`}>
        {stages.map((s, i) => {
          const y = i * rowH;
          const barW = Math.max(x(s.amount), 2);
          const leak = s.leak ?? 0;
          const leakW = leak > 0 ? Math.min(x(leak), barW) : 0;
          const cleanW = barW - leakW;
          const prev = i > 0 ? stages[i - 1] : null;
          const convPct = prev && prev.amount > 0 ? (s.amount / prev.amount) * 100 : null;

          return (
            <g key={s.stage}>
              {/* stage header row: name (left) + amount (right) */}
              <text x={0} y={y - 12} fontFamily="var(--font-mono)" fontSize={13} fontWeight={700} fill="var(--fg-1)" style={{ textTransform: "uppercase" }}>
                {s.stage}
              </text>
              <text x={innerW} y={y - 12} textAnchor="end" fontFamily="var(--font-mono)" fontSize={16} fontWeight={700} fill="var(--fg-1)">
                {formatValue(s.amount)}
              </text>

              {/* bar: managed/clean portion + leak tail */}
              <rect x={0} y={y} width={cleanW} height={barH} rx={3} fill="var(--db-navy-800)" opacity={0.9} />
              {leakW > 0 && (
                <rect x={cleanW} y={y} width={leakW} height={barH} rx={3} fill="var(--db-lava-600)" opacity={0.85} />
              )}

              {/* line below bar: caption (left) + conversion vs prior stage (right) */}
              <text x={0} y={y + barH + 20} fontFamily="var(--font-mono)" fontSize={12} fill="var(--fg-3)">
                {s.caption}
              </text>
              {convPct != null && (
                <text x={innerW} y={y + barH + 20} textAnchor="end" fontFamily="var(--font-mono)" fontSize={12} fill="var(--fg-3)">
                  ↓ {convPct.toFixed(0)}% of {prev!.stage.toLowerCase()}
                </text>
              )}

              {/* leak annotation on its own line (left, red) — never collides */}
              {leak > 0 && s.leak_label && (
                <text x={0} y={y + barH + 40} fontFamily="var(--font-mono)" fontSize={12} fontWeight={600} fill="var(--db-lava-600)">
                  {formatValue(leak)} {s.leak_label}
                </text>
              )}
            </g>
          );
        })}
      </g>
    </svg>
  );
}
