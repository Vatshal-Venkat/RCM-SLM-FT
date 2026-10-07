"use client";

import { CalendarRange, Filter, RotateCcw } from "lucide-react";
import { useMemo } from "react";

import { useApi } from "@/hooks/useApi";
import { titleCase } from "@/lib/format";
import type { FilterOptions, Filters } from "@/types/api";

export type Preset = "30" | "90" | "180" | "365" | "custom";

export interface FilterState {
  preset: Preset;
  start?: string;
  end?: string;
  payer: string;
  provider: string;
  status: string;
}

export const DEFAULT_FILTERS: FilterState = { preset: "90", payer: "", provider: "", status: "" };

function shift(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

/** Convert UI filter state to API filters, anchoring presets to the dataset's as-of date. */
export function toApiFilters(s: FilterState, asOf?: string): Filters {
  const f: Filters = {};
  if (s.preset === "custom") {
    f.start_date = s.start;
    f.end_date = s.end;
  } else if (asOf) {
    f.end_date = asOf;
    f.start_date = shift(asOf, Number(s.preset) - 1);
  }
  if (s.payer) f.payer_id = [s.payer];
  if (s.provider) f.provider_id = [s.provider];
  if (s.status) f.status = [s.status];
  return f;
}

const selectCls = "h-9 rounded-lg border border-line bg-surface-2 px-2.5 text-sm text-ink outline-none focus:border-accent/60 focus:ring-2 focus:ring-accent/20";

export function useFilterOptions() {
  return useApi<FilterOptions>("/api/analytics/filters");
}

export function FilterBar({ value, onChange, options, showStatus = true }: {
  value: FilterState; onChange: (v: FilterState) => void; options: FilterOptions | null; showStatus?: boolean;
}) {
  const presets: { id: Preset; label: string }[] = useMemo(() => [
    { id: "30", label: "30D" }, { id: "90", label: "90D" }, { id: "180", label: "6M" }, { id: "365", label: "12M" },
    { id: "custom", label: "Custom" },
  ], []);
  const dirty = JSON.stringify(value) !== JSON.stringify(DEFAULT_FILTERS);

  return (
    <div className="glass mb-6 flex flex-wrap items-center gap-2 rounded-2xl p-2.5">
      <div className="flex items-center gap-1 rounded-xl bg-surface-2 p-1" role="group" aria-label="Date range">
        <CalendarRange className="mx-1.5 h-4 w-4 text-ink-3" aria-hidden />
        {presets.map((p) => (
          <button key={p.id} onClick={() => onChange({ ...value, preset: p.id,
            start: p.id === "custom" ? value.start ?? (options ? shift(options.as_of, 89) : undefined) : undefined,
            end: p.id === "custom" ? value.end ?? options?.as_of : undefined })}
            aria-pressed={value.preset === p.id}
            className={`rounded-lg px-2.5 py-1 text-xs font-medium transition-colors ${value.preset === p.id ? "bg-accent/20 text-ink ring-1 ring-inset ring-accent/40" : "text-ink-2 hover:bg-white/5"}`}>
            {p.label}
          </button>
        ))}
      </div>
      {value.preset === "custom" && (
        <div className="flex items-center gap-1.5">
          <input type="date" aria-label="Start date" className={selectCls} value={value.start ?? ""} min={options?.date_range.min ?? undefined}
            max={value.end} onChange={(e) => onChange({ ...value, start: e.target.value })} />
          <span className="text-ink-3">–</span>
          <input type="date" aria-label="End date" className={selectCls} value={value.end ?? ""} min={value.start}
            max={options?.as_of} onChange={(e) => onChange({ ...value, end: e.target.value })} />
        </div>
      )}
      <Filter className="ml-1 h-4 w-4 text-ink-3" aria-hidden />
      <select aria-label="Payer" className={selectCls} value={value.payer} onChange={(e) => onChange({ ...value, payer: e.target.value })}>
        <option value="">All payers</option>
        {options?.payers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
      <select aria-label="Provider" className={selectCls} value={value.provider} onChange={(e) => onChange({ ...value, provider: e.target.value })}>
        <option value="">All providers</option>
        {options?.providers.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
      </select>
      {showStatus && (
        <select aria-label="Claim status" className={selectCls} value={value.status} onChange={(e) => onChange({ ...value, status: e.target.value })}>
          <option value="">All statuses</option>
          {options?.statuses.map((s) => <option key={s} value={s}>{titleCase(s)}</option>)}
        </select>
      )}
      {dirty && (
        <button onClick={() => onChange(DEFAULT_FILTERS)} className="ml-auto inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs text-ink-2 hover:bg-white/5">
          <RotateCcw className="h-3.5 w-3.5" /> Reset
        </button>
      )}
      {options && <span className="ml-auto hidden text-[11px] text-ink-3 xl:inline">Data as of {options.as_of} · synthetic</span>}
    </div>
  );
}
