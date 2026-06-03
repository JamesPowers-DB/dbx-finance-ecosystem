import React from "react";
import { MetricTooltip, type MetricTooltipContent } from "./MetricTooltip";

// Inline label + optional info icon used inside table <th> cells and small
// label rows. Keeps consistent gap and vertical alignment so the icon never
// breaks the line height when present, and produces zero markup overhead
// when absent.
interface HeaderLabelProps {
  label: React.ReactNode;
  tooltip?: MetricTooltipContent;
  placement?: "bottom" | "top" | "bottom-right" | "bottom-left";
}

export function HeaderLabel({ label, tooltip, placement }: HeaderLabelProps) {
  if (!tooltip) return <>{label}</>;
  return (
    <span style={{ display: "inline-flex", alignItems: "center", gap: 4 }}>
      {label}
      <MetricTooltip content={tooltip} placement={placement} />
    </span>
  );
}
