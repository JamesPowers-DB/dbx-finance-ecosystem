import React from "react";

interface BtnProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  children: React.ReactNode;
}

export function PrimaryBtn({ children, style, disabled, ...rest }: BtnProps) {
  return (
    <button
      {...rest}
      disabled={disabled}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--space-2)",
        padding: "var(--space-2) var(--space-4)",
        background: disabled ? "var(--border)" : "var(--db-lava-600)",
        color: "var(--fg-on-dark)",
        borderRadius: "var(--radius-sm)",
        fontFamily: "var(--font-sans)",
        fontSize: "var(--fs-body-sm)",
        fontWeight: 600,
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "background var(--dur-fast)",
        ...style,
      }}
    >
      {children}
    </button>
  );
}

export function SecondaryBtn({ children, style, disabled, ...rest }: BtnProps) {
  return (
    <button
      {...rest}
      disabled={disabled}
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "var(--space-2)",
        padding: "var(--space-2) var(--space-4)",
        background: "transparent",
        color: disabled ? "var(--fg-3)" : "var(--fg-1)",
        border: `1px solid ${disabled ? "var(--border)" : "var(--border-strong)"}`,
        borderRadius: "var(--radius-sm)",
        fontFamily: "var(--font-sans)",
        fontSize: "var(--fs-body-sm)",
        fontWeight: 500,
        cursor: disabled ? "not-allowed" : "pointer",
        transition: "border-color var(--dur-fast), background var(--dur-fast)",
        ...style,
      }}
    >
      {children}
    </button>
  );
}

export function Pill({ children, active, onClick, style }: {
  children: React.ReactNode;
  active?: boolean;
  onClick?: () => void;
  style?: React.CSSProperties;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        display: "inline-flex",
        alignItems: "center",
        padding: "var(--space-1) var(--space-3)",
        background: active ? "var(--db-navy-800)" : "var(--bg-subtle)",
        color: active ? "var(--fg-on-dark)" : "var(--fg-2)",
        borderRadius: "var(--radius-pill)",
        fontFamily: "var(--font-mono)",
        fontSize: "var(--fs-caption)",
        fontWeight: 500,
        cursor: "pointer",
        border: "none",
        transition: "background var(--dur-fast), color var(--dur-fast)",
        ...style,
      }}
    >
      {children}
    </button>
  );
}

export function SegSelect({ options, value, onChange }: {
  options: { label: string; value: string }[];
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <div style={{ display: "flex", gap: "var(--space-1)" }}>
      {options.map((opt) => (
        <Pill key={opt.value} active={value === opt.value} onClick={() => onChange(opt.value)}>
          {opt.label}
        </Pill>
      ))}
    </div>
  );
}
