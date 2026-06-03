import React from "react";

interface CardProps {
  children: React.ReactNode;
  accent?: string;
  accent2?: string;
  hover?: boolean;
  onClick?: () => void;
  style?: React.CSSProperties;
  padding?: string | number;
}

export function Card({ children, accent, accent2, hover, onClick, style, padding }: CardProps) {
  const [hovered, setHovered] = React.useState(false);
  const Tag = onClick ? "button" : "div";

  return (
    <Tag
      onClick={onClick}
      onMouseEnter={hover ? () => setHovered(true) : undefined}
      onMouseLeave={hover ? () => setHovered(false) : undefined}
      style={{
        position: "relative",
        background: "var(--bg-canvas)",
        border: `1px solid ${hovered && hover ? "var(--db-lava-600)" : "var(--border)"}`,
        borderRadius: "var(--radius-lg)",
        padding: padding ?? "var(--space-5)",
        overflow: "hidden",
        transform: hovered && hover ? "translateY(-2px)" : "translateY(0)",
        boxShadow: hovered && hover ? "var(--shadow-md)" : "none",
        transition: "transform var(--dur-base) var(--ease-out), box-shadow var(--dur-base) var(--ease-out), border-color var(--dur-base)",
        cursor: onClick ? "pointer" : "default",
        textAlign: onClick ? "left" : undefined,
        width: onClick ? "100%" : undefined,
        display: "block",
        ...style,
      }}
    >
      {accent && (
        <div
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            right: 0,
            height: 4,
            background: accent2
              ? `linear-gradient(90deg, ${accent}, ${accent2})`
              : accent,
          }}
        />
      )}
      <div style={{ position: "relative", zIndex: 1 }}>{children}</div>
    </Tag>
  );
}
