export function fmtUSD(value: number | null | undefined, compact = false): string {
  if (value == null || Number.isNaN(value)) return "—";
  if (compact) {
    const abs = Math.abs(value);
    if (abs >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
    if (abs >= 1e6) return `$${(value / 1e6).toFixed(2)}M`;
    if (abs >= 1e3) return `$${(value / 1e3).toFixed(1)}k`;
  }
  return `$${Math.round(value).toLocaleString("en-US")}`;
}

export function fmtPct(value: number | string | null | undefined, digits = 1): string {
  const n = value == null ? NaN : Number(value);
  if (Number.isNaN(n)) return "—";
  return `${n.toFixed(digits)}%`;
}

export function fmtInt(value: number | null | undefined): string {
  if (value == null || Number.isNaN(value)) return "—";
  return Math.round(value).toLocaleString("en-US");
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return iso.length >= 10 ? iso.slice(0, 10) : iso;
}

export function fmtDelta(value: number | string | null | undefined, digits = 1): string {
  const n = value == null ? NaN : Number(value);
  if (Number.isNaN(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(digits)}%`;
}

export function deltaClass(value: number | null | undefined): "pos" | "neg" | "dim" {
  if (value == null || Number.isNaN(value)) return "dim";
  if (value > 0) return "pos";
  if (value < 0) return "neg";
  return "dim";
}

export function fmtDays(days: number | null | undefined): string {
  if (days == null || Number.isNaN(days)) return "—";
  if (days < 0) return `${Math.abs(days)}d overdue`;
  if (days === 0) return "today";
  return `${days}d`;
}
