"use client";

import clsx from "clsx";
import { useState } from "react";

import { AreaTrend, BarList, MonthlyBars, SERIES, TrendChart } from "@/components/charts/Charts";
import { DEFAULT_FILTERS, FilterBar, type FilterState, toApiFilters, useFilterOptions } from "@/components/dashboard/FilterBar";
import { PayerTable } from "@/components/dashboard/PayerTable";
import { Card, CardHeader, ErrorState, PageHeader, Skeleton } from "@/components/ui/primitives";
import { useApi } from "@/hooks/useApi";
import { filtersToParams, toQuery } from "@/lib/api";
import { pct, usdCompact } from "@/lib/format";
import type { PayersAnalytics, PaymentsAnalytics, ProvidersAnalytics } from "@/types/api";

export default function AnalyticsPage() {
  const [filters, setFilters] = useState<FilterState>({ ...DEFAULT_FILTERS, preset: "365" });
  const [tab, setTab] = useState<"payer" | "provider">("payer");
  const opts = useFilterOptions();
  const q = opts.data ? toQuery(filtersToParams(toApiFilters(filters, opts.data.as_of))) : null;
  const payers = useApi<PayersAnalytics>(q !== null ? `/api/analytics/payers${q}` : null);
  const providers = useApi<ProvidersAnalytics>(q !== null ? `/api/analytics/providers${q}` : null);
  const payments = useApi<PaymentsAnalytics>(q !== null ? `/api/analytics/payments${q}` : null);

  const rows = tab === "payer" ? payers.data?.payers : providers.data?.providers;
  const error = opts.error || payers.error || providers.error || payments.error;
  const retry = () => { opts.reload(); payers.reload(); providers.reload(); payments.reload(); };

  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader eyebrow="Analytics" title="Payer & provider analytics"
        description="Performance by payer and by provider, with cash collected and accounts receivable over time. All figures are computed in SQL." />

      <FilterBar value={filters} onChange={setFilters} options={opts.data} showStatus={false} />
      {error && <ErrorState message={error} onRetry={retry} />}

      <Card className="mb-4">
        <CardHeader title={tab === "payer" ? "Payer performance" : "Provider performance"}
          subtitle={payers.data ? `Claims submitted ${payers.data.period.start} → ${payers.data.period.end} · the worst value per column is flagged` : undefined}
          right={
            <div className="flex rounded-lg bg-surface-2 p-1 text-xs" role="tablist">
              {(["payer", "provider"] as const).map((t) => (
                <button key={t} role="tab" aria-selected={tab === t} onClick={() => setTab(t)}
                  className={clsx("rounded-md px-3 py-1 font-medium", tab === t ? "bg-accent/20 text-ink ring-1 ring-inset ring-accent/40" : "text-ink-2 hover:text-ink")}>
                  {t === "payer" ? "Payers" : "Providers"}
                </button>
              ))}
            </div>
          } />
        {rows ? <PayerTable rows={rows} entity={tab === "payer" ? "Payer" : "Provider"} /> : <Skeleton className="m-4 h-64" />}
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Cash collected" subtitle="Payer and patient payments by payment month" />
          {payments.data ? (
            <MonthlyBars data={payments.data.over_time} format={usdCompact}
              series={[{ key: "payer_paid", label: "Payer payments", color: SERIES[0] }, { key: "patient_paid", label: "Patient payments", color: SERIES[2] }]} />
          ) : <Skeleton className="m-4 h-52" />}
        </Card>
        <Card>
          <CardHeader title="Outstanding AR" subtitle="Point-in-time AR at each month end" />
          {payments.data ? <AreaTrend data={payments.data.ar_over_time} dataKey="outstanding_ar" label="Outstanding AR" color={SERIES[0]} format={usdCompact} />
            : <Skeleton className="m-4 h-52" />}
        </Card>
        <Card>
          <CardHeader title="Days in AR" subtitle="AR / average daily charges (trailing 90 days)" />
          {payments.data ? <TrendChart data={payments.data.ar_over_time} series={[{ key: "days_in_ar", label: "Days in AR", color: SERIES[3] }]} format={(v) => v.toFixed(0)} />
            : <Skeleton className="m-4 h-52" />}
        </Card>
        <Card>
          <CardHeader title={tab === "payer" ? "Payment rate by payer" : "Payment rate by provider"} subtitle="Collected / billed for claims in the period" />
          {rows ? (
            <BarList format={(v) => pct(v)} color={SERIES[2]}
              rows={[...rows].sort((a, b) => (b.payment_rate ?? 0) - (a.payment_rate ?? 0))
                .map((r) => ({ label: r.name, sublabel: `${usdCompact(r.collected)} of ${usdCompact(r.billed)}`, value: r.payment_rate ?? 0 }))} />
          ) : <Skeleton className="m-4 h-52" />}
        </Card>
      </div>
    </div>
  );
}
