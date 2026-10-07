import type { Unit } from "@/types/api";

const usd0 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
const usd2 = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", minimumFractionDigits: 2 });
const int = new Intl.NumberFormat("en-US");

export function usd(v: number | null | undefined, cents = false): string {
  if (v === null || v === undefined) return "—";
  return cents ? usd2.format(v) : usd0.format(v);
}

export function usdCompact(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  const a = Math.abs(v);
  if (a >= 1e6) return `$${(v / 1e6).toFixed(2)}M`;
  if (a >= 1e3) return `$${(v / 1e3).toFixed(a >= 1e5 ? 0 : 1)}K`;
  return usd0.format(v);
}

export function pct(v: number | null | undefined, digits = 1): string {
  return v === null || v === undefined ? "—" : `${v.toFixed(digits)}%`;
}

export function num(v: number | null | undefined): string {
  return v === null || v === undefined ? "—" : int.format(v);
}

export function formatValue(v: number | null, unit: Unit, compact = false): string {
  switch (unit) {
    case "usd":
      return compact ? usdCompact(v) : usd(v);
    case "pct":
      return pct(v);
    case "days":
      return v === null ? "—" : `${v.toFixed(1)}`;
    default:
      return num(v);
  }
}

export function monthLabel(m: string): string {
  const [y, mo] = m.split("-").map(Number);
  return new Date(Date.UTC(y, mo - 1, 1)).toLocaleString("en-US", { month: "short", year: "2-digit", timeZone: "UTC" });
}

export function dateLabel(d: string | null | undefined): string {
  if (!d) return "—";
  return new Date(`${d}T00:00:00Z`).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric", timeZone: "UTC" });
}

export function titleCase(s: string | null | undefined): string {
  if (!s) return "—";
  return s.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
