import React from "react";

type MarkKind = "bars" | "pulse" | "orbit" | "climb" | "pop" | "gauge";

interface AnimatedTileMarkProps {
  kind: MarkKind;
  accent?: string;
  accent2?: string;
  size?: number;
}

export function AnimatedTileMark({
  kind,
  accent = "var(--db-lava-600)",
  accent2 = "var(--db-yellow-600)",
  size = 56,
}: AnimatedTileMarkProps) {
  const w = size;
  const h = Math.round(size * 0.85);

  if (kind === "bars") {
    return (
      <svg width={w} height={h} viewBox="0 0 56 48" fill="none" aria-hidden="true">
        {[8, 18, 28, 38, 48].map((x, i) => (
          <rect
            key={x}
            x={x - 4}
            y={0}
            width={8}
            height={48}
            rx={3}
            fill={i % 2 === 0 ? accent : accent2}
            style={{
              transformOrigin: `${x}px 48px`,
              animation: `home-bar ${1.4 + i * 0.3}s ease-in-out infinite ${i * 0.15}s`,
            }}
          />
        ))}
      </svg>
    );
  }

  if (kind === "pulse") {
    return (
      <svg width={w} height={w} viewBox="0 0 56 56" fill="none" aria-hidden="true">
        <circle cx={28} cy={28} r={20} stroke={accent} strokeWidth={2} opacity={0.2}
          style={{ animation: "home-pop 2s ease-in-out infinite" }} />
        <circle cx={28} cy={28} r={13} stroke={accent} strokeWidth={2} opacity={0.5}
          style={{ animation: "home-pop 2s ease-in-out infinite 0.4s" }} />
        <circle cx={28} cy={28} r={6} fill={accent}
          style={{ animation: "home-pulse 2s ease-in-out infinite 0.8s" }} />
      </svg>
    );
  }

  if (kind === "orbit") {
    return (
      <svg width={w} height={w} viewBox="0 0 56 56" fill="none" aria-hidden="true">
        <circle cx={28} cy={28} r={18} stroke={accent} strokeWidth={1.5} opacity={0.3} />
        <circle cx={28} cy={10} r={5} fill={accent}
          style={{ transformOrigin: "28px 28px", animation: "home-spin 3s linear infinite" }} />
        <circle cx={28} cy={28} r={7} fill={accent2} opacity={0.8} />
      </svg>
    );
  }

  if (kind === "climb") {
    return (
      <svg width={w} height={h} viewBox="0 0 56 48" fill="none" aria-hidden="true">
        <polyline
          points="4,44 14,30 24,20 34,24 44,10 52,4"
          stroke={accent}
          strokeWidth={2.5}
          strokeLinecap="round"
          strokeLinejoin="round"
          style={{ animation: "home-float 3s ease-in-out infinite" }}
        />
        <circle cx={52} cy={4} r={4} fill={accent}
          style={{ animation: "home-pulse 2s ease-in-out infinite" }} />
      </svg>
    );
  }

  if (kind === "pop") {
    return (
      <svg width={w} height={w} viewBox="0 0 56 56" fill="none" aria-hidden="true">
        <rect x={10} y={20} width={16} height={26} rx={3} fill={accent} opacity={0.7}
          style={{ animation: "home-bar 1.8s ease-in-out infinite" }} />
        <rect x={30} y={10} width={16} height={36} rx={3} fill={accent2}
          style={{ animation: "home-bar 1.8s ease-in-out infinite 0.5s" }} />
      </svg>
    );
  }

  // gauge
  return (
    <svg width={w} height={Math.round(h * 0.65)} viewBox="0 0 56 32" fill="none" aria-hidden="true">
      <path d="M4 28A24 24 0 0 1 52 28" stroke="var(--border)" strokeWidth={3} strokeLinecap="round" />
      <path d="M4 28A24 24 0 0 1 40 8" stroke={accent} strokeWidth={3} strokeLinecap="round"
        style={{ animation: "home-float 4s ease-in-out infinite" }} />
      <circle cx={28} cy={28} r={4} fill={accent} />
    </svg>
  );
}
