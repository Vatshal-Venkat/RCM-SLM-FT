import clsx from "clsx";
import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import { Sparkline } from "@/components/charts/Charts";
import { formatValue } from "@/lib/format";
import type { KpiCard as Kpi } from "@/types/api";

export function KpiCard({ kpi, spark, index = 0 }: { kpi: Kpi; spark?: (number | null)[]; index?: number }) {
  const { change, better, unit, change_kind } = kpi;
  const flat = change === null || Math.abs(change) < 0.05;
  const up = (change ?? 0) > 0;
  const good = better === "neutral" || flat ? null : (better === "up") === up;
  const Icon = flat ? Minus : up ? ArrowUpRight : ArrowDownRight;
  const changeText = change === null ? "no prior data"
    : `${up ? "+" : ""}${change.toFixed(1)}${change_kind === "points" ? (unit === "days" ? " days" : " pts") : "%"}`;

  return (
    <div className="glass group relative overflow-hidden rounded-2xl p-4 animate-fade-up" style={{ animationDelay: `${index * 40}ms` }}
      title={kpi.formula}>
      <div className="pointer-events-none absolute -right-10 -top-10 h-28 w-28 rounded-full bg-accent/10 blur-2xl transition-opacity group-hover:opacity-100 opacity-60" />
      <p className="text-xs font-medium text-ink-3">{kpi.label}</p>
      <div className="mt-2 flex items-end justify-between gap-2">
        <p className="text-2xl font-semibold tracking-tight text-ink">
          {formatValue(kpi.value, unit, true)}
          {unit === "days" && kpi.value !== null && <span className="ml-1 text-sm font-normal text-ink-3">days</span>}
        </p>
        {spark && <Sparkline values={spark} color="var(--series-1)" />}
      </div>
      <div className="mt-2 flex items-center gap-1.5 text-xs">
        <span className={clsx("inline-flex items-center gap-0.5 font-medium",
          good === null ? "text-ink-3" : good ? "text-good" : "text-critical")}>
          <Icon className="h-3.5 w-3.5" aria-hidden />
          {changeText}
        </span>
        <span className="text-ink-3">vs prior period</span>
        {good !== null && <span className="sr-only">{good ? "(improving)" : "(worsening)"}</span>}
      </div>
    </div>
  );
}
