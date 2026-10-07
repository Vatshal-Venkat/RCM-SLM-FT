"use client";

import { ArrowDown, ArrowUp } from "lucide-react";
import { useMemo, useState } from "react";

import { num, pct, usdCompact } from "@/lib/format";
import type { EntityPerformance } from "@/types/api";

type Col = { key: keyof EntityPerformance; label: string; fmt: (v: number | null) => string; worse?: "high" | "low" };

const COLS: Col[] = [
  { key: "claims", label: "Claims", fmt: (v) => num(v) },
  { key: "billed", label: "Billed", fmt: (v) => usdCompact(v) },
  { key: "collected", label: "Collected", fmt: (v) => usdCompact(v) },
  { key: "denial_rate", label: "Denial rate", fmt: (v) => pct(v), worse: "high" },
  { key: "clean_claim_rate", label: "Clean claim", fmt: (v) => pct(v), worse: "low" },
  { key: "first_pass_resolution_rate", label: "First pass", fmt: (v) => pct(v), worse: "low" },
  { key: "avg_days_to_adjudicate", label: "Days to adjudicate", fmt: (v) => (v === null ? "—" : v.toFixed(1)), worse: "high" },
  { key: "pending_claims", label: "Pending", fmt: (v) => num(v) },
  { key: "outstanding_ar", label: "Open AR", fmt: (v) => usdCompact(v), worse: "high" },
];

/** Sortable entity table; the worst value in "worse"-tagged columns is flagged with an icon + colour. */
export function PayerTable({ rows, entity = "Payer" }: { rows: EntityPerformance[]; entity?: string }) {
  const [sort, setSort] = useState<{ key: keyof EntityPerformance; desc: boolean }>({ key: "billed", desc: true });
  const sorted = useMemo(() => [...rows].sort((a, b) => {
    const x = (a[sort.key] as number) ?? -Infinity, y = (b[sort.key] as number) ?? -Infinity;
    return sort.desc ? y - x : x - y;
  }), [rows, sort]);
  const worst = useMemo(() => {
    const w: Partial<Record<keyof EntityPerformance, string>> = {};
    for (const c of COLS.filter((c) => c.worse)) {
      const vals = rows.filter((r) => r[c.key] !== null);
      if (!vals.length) continue;
      const pick = vals.reduce((m, r) => ((c.worse === "high" ? (r[c.key] as number) > (m[c.key] as number) : (r[c.key] as number) < (m[c.key] as number)) ? r : m));
      w[c.key] = pick.id;
    }
    return w;
  }, [rows]);

  return (
    <div className="overflow-x-auto px-2 pb-3">
      <table className="w-full min-w-[860px] text-sm">
        <thead>
          <tr className="text-left text-xs text-ink-3">
            <th className="px-3 py-2 font-medium">{entity}</th>
            {COLS.map((c) => (
              <th key={c.key} className="px-3 py-2 text-right font-medium">
                <button className="inline-flex items-center gap-1 hover:text-ink" onClick={() => setSort({ key: c.key, desc: sort.key === c.key ? !sort.desc : true })}>
                  {c.label}
                  {sort.key === c.key && (sort.desc ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />)}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="tabular">
          {sorted.map((r) => (
            <tr key={r.id} className="border-t border-line hover:bg-white/[0.02]">
              <td className="px-3 py-2.5 text-ink">{r.name}</td>
              {COLS.map((c) => {
                const flagged = worst[c.key] === r.id;
                return (
                  <td key={c.key} className={`px-3 py-2.5 text-right ${flagged ? "font-semibold text-critical" : "text-ink-2"}`}
                    title={flagged ? `Worst ${c.label.toLowerCase()} among ${entity.toLowerCase()}s` : undefined}>
                    {flagged && <span aria-hidden>▲ </span>}{c.fmt(r[c.key] as number | null)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
