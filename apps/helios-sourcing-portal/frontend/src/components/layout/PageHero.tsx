import React from "react";

interface PageHeroProps {
  eyebrow: string;
  title: string;
  subtitle?: string;
  right?: React.ReactNode;
}

export function PageHero({ eyebrow, title, subtitle, right }: PageHeroProps) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "flex-start",
        justifyContent: "space-between",
        gap: "var(--space-5)",
        marginBottom: "var(--space-6)",
      }}
    >
      <div>
        <div
          style={{
            display: "inline-flex",
            alignItems: "center",
            gap: "var(--space-2)",
            marginBottom: "var(--space-3)",
          }}
        >
          <span
            style={{
              display: "inline-block",
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: "var(--db-lava-600)",
              animation: "home-pulse 2.4s ease-in-out infinite",
            }}
          />
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: "var(--fs-eyebrow)",
              fontWeight: 500,
              color: "var(--fg-2)",
              letterSpacing: "var(--tracking-eyebrow)",
              textTransform: "uppercase",
            }}
          >
            {eyebrow}
          </span>
        </div>
        <h1
          style={{
            fontSize: 36,
            fontWeight: 700,
            color: "var(--fg-1)",
            letterSpacing: "var(--tracking-tight)",
            lineHeight: "var(--lh-tight)",
            marginBottom: subtitle ? "var(--space-2)" : 0,
          }}
        >
          {title}
        </h1>
        {subtitle && (
          <p style={{ fontSize: "var(--fs-body-sm)", color: "var(--fg-2)", lineHeight: "var(--lh-normal)" }}>
            {subtitle}
          </p>
        )}
      </div>
      {right && (
        <div style={{ display: "flex", alignItems: "center", gap: "var(--space-2)", flexShrink: 0 }}>
          {right}
        </div>
      )}
    </div>
  );
}
