import React, { useCallback, useRef, useState } from "react";
import { createPortal } from "react-dom";

// Structured tooltip content. Every metric in the catalog conforms to this
// shape so the popover renders a consistent Period / Definition / Formula /
// Filters grid that demo audiences can read without context-switching.
export interface MetricTooltipContent {
  metric: string;
  period: string;
  definition: string;
  formula?: string;
  filters?: string;
}

interface MetricTooltipProps {
  content: MetricTooltipContent;
  // Use children when wrapping an existing UI element (Pill, status text,
  // strip dot, etc.). When omitted, a default circled-i glyph trigger is
  // rendered inline so it can sit beside a label.
  children?: React.ReactNode;
  iconSize?: number;
  // Hint for initial placement; the component still auto-flips against
  // viewport edges. Kept for API compatibility with earlier call sites.
  placement?: "bottom" | "top" | "bottom-right" | "bottom-left";
  // When the trigger is itself an interactive element (e.g. a Pill button
  // that selects a tab) we shouldn't tabindex the wrapper too — keep the
  // child's natural focus path and only react to hover.
  hoverOnly?: boolean;
}

interface Coords {
  top: number;
  left: number;
}

// Conservative popover size estimate used for viewport-edge math before the
// popover is measured. Actual rendered height auto-grows; this only affects
// whether we initially flip above vs below.
const POPOVER_W = 280;
const POPOVER_H_EST = 200;
const VIEWPORT_MARGIN = 8;
const TRIGGER_GAP = 6;

export function MetricTooltip({
  content,
  children,
  iconSize = 12,
  placement = "bottom",
  hoverOnly = false,
}: MetricTooltipProps) {
  const triggerRef = useRef<HTMLSpanElement>(null);
  const [show, setShow] = useState(false);
  const [coords, setCoords] = useState<Coords | null>(null);

  // Compute the popover's fixed-position coordinates from the trigger's
  // bounding rect. Auto-flips:
  //   - right-align if the popover would overflow the viewport right edge
  //   - flip above if it would overflow the viewport bottom edge
  // We use position: fixed (relative to the viewport) so the popover
  // escapes every ancestor overflow context — table horizontal scroll
  // wrappers, the page's main scroll container, and drilldown panels.
  const computeCoords = useCallback(() => {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;

    // Default: left edge of trigger, below by TRIGGER_GAP.
    let left = rect.left;
    let top = rect.bottom + TRIGGER_GAP;

    // Honor explicit *-right hint by starting right-aligned.
    if (placement === "bottom-right") {
      left = rect.right - POPOVER_W;
    }

    // Right-edge guard.
    if (left + POPOVER_W > window.innerWidth - VIEWPORT_MARGIN) {
      left = Math.max(VIEWPORT_MARGIN, rect.right - POPOVER_W);
    }
    // Left-edge guard (when the right-aligned variant pushed past 0).
    if (left < VIEWPORT_MARGIN) {
      left = VIEWPORT_MARGIN;
    }

    // Bottom-edge guard — flip above the trigger.
    if (placement === "top" || top + POPOVER_H_EST > window.innerHeight - VIEWPORT_MARGIN) {
      top = rect.top - POPOVER_H_EST - TRIGGER_GAP;
      if (top < VIEWPORT_MARGIN) {
        // No room above either — clamp to top of viewport.
        top = VIEWPORT_MARGIN;
      }
    }

    setCoords({ top, left });
  }, [placement]);

  const open = useCallback(() => {
    computeCoords();
    setShow(true);
  }, [computeCoords]);

  const close = useCallback(() => setShow(false), []);

  const trigger = children ?? (
    <span
      aria-label={`More info about ${content.metric}`}
      role="img"
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: iconSize,
        height: iconSize,
        borderRadius: "50%",
        border: "1px solid var(--fg-3)",
        color: "var(--fg-3)",
        fontFamily: "var(--font-mono)",
        fontSize: Math.max(8, iconSize - 4),
        fontWeight: 700,
        lineHeight: 1,
        cursor: "help",
        userSelect: "none",
      }}
    >
      i
    </span>
  );

  return (
    <>
      <span
        ref={triggerRef}
        tabIndex={hoverOnly ? undefined : 0}
        onMouseEnter={open}
        onMouseLeave={close}
        onFocus={open}
        onBlur={close}
        style={{
          display: "inline-flex",
          alignItems: "center",
          outline: "none",
        }}
      >
        {trigger}
      </span>
      {show && coords && createPortal(
        <div
          role="tooltip"
          style={{
            position: "fixed",
            top: coords.top,
            left: coords.left,
            width: POPOVER_W,
            zIndex: 1000,
            // Never steal clicks from the trigger / underlying Pill or row.
            pointerEvents: "none",
            background: "var(--bg-canvas)",
            border: "1px solid var(--border)",
            borderLeft: "3px solid var(--db-lava-600)",
            borderRadius: "var(--radius-sm)",
            boxShadow: "var(--shadow-2)",
            padding: "var(--space-3) var(--space-4)",
            fontFamily: "var(--font-sans)",
            fontSize: 12,
            color: "var(--fg-1)",
            lineHeight: 1.4,
          }}
        >
          <div
            style={{
              fontWeight: 700,
              fontSize: 13,
              marginBottom: "var(--space-2)",
              color: "var(--fg-1)",
            }}
          >
            {content.metric}
          </div>
          <TooltipField label="Period" value={content.period} />
          <TooltipField label="Definition" value={content.definition} />
          {content.formula && <TooltipField label="Formula" value={content.formula} mono />}
          {content.filters && <TooltipField label="Filters" value={content.filters} mono />}
        </div>,
        document.body,
      )}
    </>
  );
}

function TooltipField({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div style={{ marginBottom: "var(--space-1)" }}>
      <div
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 9,
          color: "var(--fg-3)",
          textTransform: "uppercase",
          letterSpacing: "0.06em",
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontFamily: mono ? "var(--font-mono)" : "var(--font-sans)",
          fontSize: mono ? 11 : 12,
          color: "var(--fg-2)",
          marginTop: 1,
          wordBreak: mono ? "break-word" : "normal",
        }}
      >
        {value}
      </div>
    </div>
  );
}
