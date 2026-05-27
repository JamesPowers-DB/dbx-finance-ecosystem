import React from "react";
import { MetricTooltip, type MetricTooltipContent } from "./MetricTooltip";

interface StatTileProps {
  label: string;
  value: string;
  delta?: string;
  deltaPositive?: boolean;
  sub?: string;
  accent?: string;
  // Optional metric-definition tooltip. When set, an info icon renders
  // inline after the label and surfaces period/definition/formula/filters
  // on hover or keyboard focus.
  tooltip?: MetricTooltipContent;
}

export function StatTile({ label, value, delta, deltaPositive, sub, accent, tooltip }: StatTileProps) {
  return (
    <div
      style={{
        background: "var(--bg-canvas)",
        border: "1px solid var(--border)",
        borderRadius: "var(--radius-lg)",
        padding: "var(--space-5)",
        display: "flex",
        flexDirection: "column",
        gap: "var(--space-2)",
        minWidth: 160,
        flex: 1,
      }}
    >
      {accent && (
        <div
          style={{
            width: 24,
            height: 3,
            borderRadius: 2,
            background: accent,
            marginBottom: "var(--space-1)",
          }}
        />
      )}
      <span
        style={{
          fontSize: "var(--fs-caption)",
          fontFamily: "var(--font-mono)",
          color: "var(--fg-2)",
          textTransform: "uppercase",
          letterSpacing: "var(--tracking-eyebrow)",
          display: "inline-flex",
          alignItems: "center",
          gap: 6,
        }}
      >
        {label}
        {tooltip && <MetricTooltip content={tooltip} />}
      </span>
      <span
        style={{
          fontSize: "var(--fs-h2)",
          fontFamily: "var(--font-display)",
          fontWeight: 700,
          color: "var(--fg-1)",
          letterSpacing: "var(--tracking-tight)",
        }}
      >
        {value}
      </span>
      {(delta || sub) && (
        <span
          style={{
            fontSize: "var(--fs-caption)",
            fontFamily: "var(--font-mono)",
            color: delta
              ? deltaPositive
                ? "var(--success)"
                : "var(--danger)"
              : "var(--fg-3)",
          }}
        >
          {delta ?? sub}
        </span>
      )}
    </div>
  );
}
