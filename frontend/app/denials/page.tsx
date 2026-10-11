"use client";

import Link from "next/link";
import { useState } from "react";

import { BarList, MonthlyBars, SERIES, TrendChart } from "@/components/charts/Charts";
import { DEFAULT_FILTERS, FilterBar, type FilterState, toApiFilters, useFilterOptions } from "@/components/dashboard/FilterBar";
import { Card, CardHeader, EmptyState, ErrorState, PageHeader, Pill, Skeleton } from "@/components/ui/primitives";
import { useApi } from "@/hooks/useApi";
import { filtersToParams, toQuery } from "@/lib/api";
import { num, pct, titleCase, usd, usdCompact } from "@/lib/format";
import type { DenialsAnalytics } from "@/types/api";

export default function DenialsPage() {
  const [filters, setFilters] = useState<FilterState>({ ...DEFAULT_FILTERS, preset: "365" });
  const opts = useFilterOptions();
  const path = opts.data ? `/api/analytics/denials${toQuery(filtersToParams(toApiFilters(filters, opts.data.as_of)))}` : null;
  const { data, error, loading, reload } = useApi<DenialsAnalytics>(path);

  const total = data?.categories.reduce((s, c) => s + c.count, 0) ?? 0;
  const deniedAmount = data?.categories.reduce((s, c) => s + c.denied_amount, 0) ?? 0;
  const preventable = data?.reasons.filter((r) => r.preventable).reduce((s, r) => s + r.count, 0) ?? 0;
  const decided = data?.reasons.reduce((s, r) => s + r.appeals_decided, 0) ?? 0;
  const overturned = data?.reasons.reduce((s, r) => s + (r.overturn_rate ?? 0) / 100 * r.appeals_decided, 0) ?? 0;

  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader eyebrow="Denials" title="Denial management"
        description="Where denials come from: categories, CARC reasons, payers and providers, with preventable share and appeal outcomes." />

      <FilterBar value={filters} onChange={setFilters} options={opts.data} showStatus={false} />
      {(error || opts.error) && <ErrorState message={error || opts.error || ""} onRetry={() => { opts.reload(); reload(); }} />}

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          ["Denied claims", num(total)],
          ["Denied amount", usdCompact(deniedAmount)],
          ["Preventable", total ? pct((preventable / total) * 100) : "—"],
          ["Appeal overturn rate", decided ? pct((overturned / decided) * 100) : "—"],
        ].map(([label, value]) => (
          <Card key={label} className="p-4">
            <p className="text-xs text-ink-3">{label}</p>
            {data ? <p className="tabular mt-1 text-2xl font-semibold text-ink">{value}</p> : <Skeleton className="mt-2 h-7 w-24" />}
          </Card>
        ))}
      </div>

      {data && (
        <div className={`grid gap-4 lg:grid-cols-2 transition-opacity ${loading ? "opacity-60" : ""}`}>
          <Card>
            <CardHeader title="Denials per month" subtitle="All denials vs preventable ones, by claim submission month" />
            <MonthlyBars data={data.over_time} stacked={false} format={num}
              series={[{ key: "denials", label: "Denials", color: SERIES[1] }, { key: "preventable", label: "Preventable", color: SERIES[3] }]} />
          </Card>
          <Card>
            <CardHeader title="Denial rate" subtitle="Denied / adjudicated claims by submission month" />
            <TrendChart data={data.over_time} series={[{ key: "denial_rate", label: "Denial rate", color: SERIES[1] }]} format={(v) => pct(v)} />
          </Card>
          <Card>
            <CardHeader title="Denial categories" subtitle="Share of denials; click through on the reason table below" />
            <BarList format={num} color={SERIES[1]}
              rows={data.categories.map((c) => ({ label: titleCase(c.category), sublabel: `${pct(c.share_pct)} · ${usdCompact(c.denied_amount)}`, value: c.count }))} />
          </Card>
          <Card>
            <CardHeader title="Denial rate by payer" />
            <BarList format={(v) => pct(v)} color={SERIES[0]} highlight={(i) => i === 0}
              rows={[...data.by_payer].sort((a, b) => (b.denial_rate ?? 0) - (a.denial_rate ?? 0))
                .map((p) => ({ label: p.name, sublabel: `${num(p.denied)} of ${num(p.adjudicated)}`, value: p.denial_rate ?? 0 }))} />
          </Card>
          <Card className="lg:col-span-2">
            <CardHeader title="Denial reasons (CARC)" subtitle="Open a category to see its claims" />
            {data.reasons.length === 0 ? <EmptyState message="No denials in this period." /> : (
              <div className="overflow-x-auto px-2 pb-3">
                <table className="w-full min-w-[900px] text-sm">
                  <thead>
                    <tr className="text-left text-xs text-ink-3">
                      {["CARC", "Description", "Category", "Denials", "Share", "Denied $", "Preventable", "Appeals decided", "Overturned"].map((h, i) => (
                        <th key={h} className={`px-3 py-2 font-medium ${i >= 3 && i !== 6 ? "text-right" : ""}`}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="tabular">
                    {data.reasons.map((r) => (
                      <tr key={`${r.group_code}-${r.carc_code}`} className="border-t border-line hover:bg-white/[0.02]">
                        <td className="px-3 py-2 text-ink">{r.group_code}-{r.carc_code}</td>
                        <td className="max-w-[320px] px-3 py-2 text-ink-2">{r.description}</td>
                        <td className="px-3 py-2">
                          <Link href={`/claims?denial_category=${r.category}`} className="text-accent hover:underline">{titleCase(r.category)}</Link>
                        </td>
                        <td className="px-3 py-2 text-right text-ink">{num(r.count)}</td>
                        <td className="px-3 py-2 text-right text-ink-2">{pct(r.share_pct)}</td>
                        <td className="px-3 py-2 text-right text-ink-2">{usd(r.denied_amount)}</td>
                        <td className="px-3 py-2">{r.preventable ? <Pill tone="warning">Preventable</Pill> : <span className="text-ink-3">—</span>}</td>
                        <td className="px-3 py-2 text-right text-ink-2">{num(r.appeals_decided)}</td>
                        <td className="px-3 py-2 text-right text-ink-2">{pct(r.overturn_rate)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
          <Card className="lg:col-span-2">
            <CardHeader title="Denial rate by provider" />
            <BarList format={(v) => pct(v)} color={SERIES[5]} highlight={(i) => i === 0}
              rows={[...data.by_provider].sort((a, b) => (b.denial_rate ?? 0) - (a.denial_rate ?? 0))
                .map((p) => ({ label: p.name, sublabel: `${num(p.denied)} of ${num(p.adjudicated)}`, value: p.denial_rate ?? 0 }))} />
          </Card>
        </div>
      )}
      {!data && loading && <div className="grid gap-4 lg:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-64 rounded-2xl" />)}</div>}
    </div>
  );
}
