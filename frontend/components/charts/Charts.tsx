"use client";

import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { monthLabel } from "@/lib/format";

export const SERIES = ["var(--series-1)", "var(--series-2)", "var(--series-3)", "var(--series-4)", "var(--series-5)", "var(--series-6)"];

const axisProps = {
  stroke: "var(--axis)",
  tick: { fill: "var(--text-muted)", fontSize: 11 },
  tickLine: false,
  axisLine: { stroke: "var(--axis)" },
} as const;

interface SeriesDef {
  key: string;
  label: string;
  color: string;
}

interface TooltipEntry {
  dataKey?: string | number;
  name?: string;
  value?: number;
  color?: string;
}

function ChartTooltip({ active, payload, label, format }: {
  active?: boolean; payload?: TooltipEntry[]; label?: string; format: (v: number) => string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-xl border border-line-strong bg-surface-2/95 px-3 py-2 text-xs shadow-xl backdrop-blur">
      <p className="mb-1 font-medium text-ink">{label ? monthLabel(String(label)) : ""}</p>
      {payload.map((p) => (
        <div key={String(p.dataKey)} className="flex items-center justify-between gap-4">
          <span className="flex items-center gap-1.5 text-ink-2">
            <span className="h-2 w-2 rounded-full" style={{ background: p.color }} aria-hidden />
            {p.name}
          </span>
          <span className="tabular font-medium text-ink">{typeof p.value === "number" ? format(p.value) : "—"}</span>
        </div>
      ))}
    </div>
  );
}

export function Legend({ series }: { series: SeriesDef[] }) {
  if (series.length < 2) return null;
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 px-5 pb-1 text-xs text-ink-2">
      {series.map((s) => (
        <span key={s.key} className="inline-flex items-center gap-1.5">
          <span className="h-2 w-3 rounded-sm" style={{ background: s.color }} aria-hidden /> {s.label}
        </span>
      ))}
    </div>
  );
}

/** Line chart over months; one y-axis, 2px lines, crosshair tooltip. */
export function TrendChart<T extends { month: string }>({ data, series, format, height = 220, domain }: {
  data: T[]; series: SeriesDef[]; format: (v: number) => string; height?: number; domain?: [number | "auto", number | "auto"];
}) {
  return (
    <div>
      <Legend series={series} />
      <div style={{ height }} className="px-2">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={data} margin={{ top: 10, right: 16, bottom: 0, left: 0 }}>
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="month" tickFormatter={monthLabel} {...axisProps} minTickGap={16} />
            <YAxis tickFormatter={(v) => format(Number(v))} {...axisProps} width={56} domain={domain ?? ["auto", "auto"]} />
            <Tooltip content={<ChartTooltip format={format} />} cursor={{ stroke: "var(--border-strong)" }} />
            {series.map((s) => (
              <Line key={s.key} type="monotone" dataKey={s.key} name={s.label} stroke={s.color} strokeWidth={2}
                dot={false} activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--surface-1)" }} connectNulls />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/** Single-series area (for a headline magnitude over time). */
export function AreaTrend<T extends { month: string }>({ data, dataKey, label, color, format, height = 220 }: {
  data: T[]; dataKey: string; label: string; color: string; format: (v: number) => string; height?: number;
}) {
  const id = `grad-${dataKey}`;
  return (
    <div style={{ height }} className="px-2">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 10, right: 16, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={id} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--grid)" vertical={false} />
          <XAxis dataKey="month" tickFormatter={monthLabel} {...axisProps} minTickGap={16} />
          <YAxis tickFormatter={(v) => format(Number(v))} {...axisProps} width={56} />
          <Tooltip content={<ChartTooltip format={format} />} cursor={{ stroke: "var(--border-strong)" }} />
          <Area type="monotone" dataKey={dataKey} name={label} stroke={color} strokeWidth={2} fill={`url(#${id})`}
            activeDot={{ r: 4, strokeWidth: 2, stroke: "var(--surface-1)" }} />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Vertical bars over months; stacked when several series. 2px gaps, rounded data-ends. */
export function MonthlyBars<T extends { month: string }>({ data, series, format, height = 220, stacked = true }: {
  data: T[]; series: SeriesDef[]; format: (v: number) => string; height?: number; stacked?: boolean;
}) {
  return (
    <div>
      <Legend series={series} />
      <div style={{ height }} className="px-2">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 10, right: 16, bottom: 0, left: 0 }} barCategoryGap="28%">
            <CartesianGrid stroke="var(--grid)" vertical={false} />
            <XAxis dataKey="month" tickFormatter={monthLabel} {...axisProps} minTickGap={16} />
            <YAxis tickFormatter={(v) => format(Number(v))} {...axisProps} width={56} />
            <Tooltip content={<ChartTooltip format={format} />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
            {series.map((s, i) => (
              <Bar key={s.key} dataKey={s.key} name={s.label} fill={s.color} stackId={stacked ? "a" : undefined}
                stroke="var(--surface-1)" strokeWidth={stacked ? 2 : 0}
                radius={!stacked || i === series.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]} maxBarSize={28} />
            ))}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

/** Horizontal ranked bar list in plain HTML: labels and values are text, bars are proportional. */
export function BarList({ rows, format, color = "var(--series-1)", highlight }: {
  rows: { label: string; sublabel?: string; value: number; title?: string }[];
  format: (v: number) => string; color?: string; highlight?: (i: number) => boolean;
}) {
  const max = Math.max(...rows.map((r) => r.value), 0) || 1;
  return (
    <ul className="space-y-2.5 px-5 pb-5">
      {rows.map((r, i) => (
        <li key={r.label + i} title={r.title} className="group">
          <div className="mb-1 flex items-baseline justify-between gap-3 text-xs">
            <span className="min-w-0 truncate text-ink-2">
              <span className="text-ink">{r.label}</span>
              {r.sublabel && <span className="ml-1.5 text-ink-3">{r.sublabel}</span>}
            </span>
            <span className="tabular shrink-0 font-medium text-ink">{format(r.value)}</span>
          </div>
          <div className="h-2 rounded-full bg-white/[0.04]">
            <div className="h-2 rounded-full transition-all group-hover:brightness-125"
              style={{ width: `${Math.max(2, (r.value / max) * 100)}%`, background: highlight?.(i) ? "var(--series-2)" : color }} />
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Tiny trend line for KPI cards (no axes; the card states the value). */
export function Sparkline({ values, color }: { values: (number | null)[]; color: string }) {
  const data = values.map((v, i) => ({ i, v }));
  if (data.filter((d) => d.v !== null).length < 2) return null;
  return (
    <div className="h-9 w-24" aria-hidden>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 4, right: 2, bottom: 4, left: 2 }}>
          <YAxis hide domain={["dataMin", "dataMax"]} />
          <Line type="monotone" dataKey="v" stroke={color} strokeWidth={1.75} dot={false} isAnimationActive={false} connectNulls />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
