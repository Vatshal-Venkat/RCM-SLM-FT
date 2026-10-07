"use client";

import { ArrowRight, Bot, Database, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { AreaTrend, BarList, MonthlyBars, SERIES, TrendChart } from "@/components/charts/Charts";
import { DEFAULT_FILTERS, FilterBar, type FilterState, toApiFilters, useFilterOptions } from "@/components/dashboard/FilterBar";
import { KpiCard } from "@/components/dashboard/KpiCard";
import { PayerTable } from "@/components/dashboard/PayerTable";
import { Card, CardHeader, ErrorState, Skeleton } from "@/components/ui/primitives";
import { useApi } from "@/hooks/useApi";
import { filtersToParams, toQuery } from "@/lib/api";
import { num, pct, titleCase, usdCompact } from "@/lib/format";
import type { Overview } from "@/types/api";

const CARD_KEYS = [
  "total_claims", "clean_claim_rate", "denial_rate", "first_pass_resolution_rate",
  "days_in_ar", "net_collection_rate", "total_paid", "outstanding_ar",
];

const QUICK_PROMPTS = [
  "Why did our denial rate increase?",
  "Which payer has the highest denial rate?",
  "What is causing our AR to increase?",
  "Which claims should we prioritize?",
];

export default function DashboardPage() {
  const [filters, setFilters] = useState<FilterState>(DEFAULT_FILTERS);
  const opts = useFilterOptions();
  const path = opts.data ? `/api/analytics/overview${toQuery(filtersToParams(toApiFilters(filters, opts.data.as_of)))}` : null;
  const { data, error, loading, reload } = useApi<Overview>(path);

  const sparks = useMemo(() => {
    if (!data) return {} as Record<string, (number | null)[]>;
    const c = data.claims_over_time.slice(-8);
    const a = data.ar_over_time.slice(-8);
    const p = data.payments_over_time.slice(-8);
    return {
      total_claims: c.map((r) => r.claims),
      clean_claim_rate: c.map((r) => r.clean_claim_rate),
      denial_rate: c.map((r) => r.denial_rate),
      first_pass_resolution_rate: c.map((r) => r.first_pass_resolution_rate),
      days_in_ar: a.map((r) => r.days_in_ar),
      outstanding_ar: a.map((r) => r.outstanding_ar),
      total_paid: p.map((r) => r.total_paid),
    } as Record<string, (number | null)[]>;
  }, [data]);

  const cards = data ? CARD_KEYS.map((k) => data.kpis.find((x) => x.key === k)!).filter(Boolean) : [];

  return (
    <div className="mx-auto max-w-[1400px]">
      <section className="glass relative mb-6 overflow-hidden rounded-3xl p-6 md:p-8 animate-fade-up">
        <div className="pointer-events-none absolute -right-24 -top-24 h-72 w-72 rounded-full bg-accent/20 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-28 left-1/3 h-64 w-64 rounded-full bg-accent-2/10 blur-3xl" />
        <div className="relative flex flex-wrap items-end justify-between gap-6">
          <div className="max-w-2xl">
            <p className="inline-flex items-center gap-1.5 rounded-full bg-white/5 px-2.5 py-1 text-[11px] font-medium text-ink-2 ring-1 ring-inset ring-white/10">
              <Sparkles className="h-3.5 w-3.5 text-accent" /> Fine-tuned RCM SLM · RAG · Deterministic analytics
            </p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight md:text-4xl">
              <span className="gradient-text">AI-powered</span> Revenue Cycle Management
            </h1>
            <p className="mt-2 text-sm text-ink-2 md:text-base">
              Executive view of claims, denials, collections and AR, with an AI Copilot that explains every number
              from your own data, grounded in validated RCM knowledge.
            </p>
            <div className="mt-4 flex flex-wrap gap-2 text-[11px] text-ink-3">
              <span className="inline-flex items-center gap-1"><Database className="h-3.5 w-3.5" /> Metrics computed in SQL, never by the model</span>
              <span className="inline-flex items-center gap-1"><ShieldCheck className="h-3.5 w-3.5" /> Every answer validated</span>
            </div>
          </div>
          <div className="w-full max-w-md">
            <p className="mb-2 text-xs font-medium text-ink-3">Ask the Copilot</p>
            <div className="grid gap-2">
              {QUICK_PROMPTS.map((q) => (
                <Link key={q} href={`/copilot?q=${encodeURIComponent(q)}`}
                  className="group flex items-center justify-between rounded-xl border border-line bg-surface-2/70 px-3 py-2 text-sm text-ink-2 transition hover:border-accent/40 hover:text-ink">
                  <span className="flex items-center gap-2"><Bot className="h-4 w-4 text-accent" /> {q}</span>
                  <ArrowRight className="h-4 w-4 opacity-0 transition group-hover:translate-x-0.5 group-hover:opacity-100" />
                </Link>
              ))}
            </div>
          </div>
        </div>
      </section>

      <FilterBar value={filters} onChange={setFilters} options={opts.data} />

      {(error || opts.error) && <ErrorState message={error || opts.error || ""} onRetry={() => { opts.reload(); reload(); }} />}

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        {loading && !data
          ? Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-[112px] rounded-2xl" />)
          : cards.map((k, i) => <KpiCard key={k.key} kpi={k} spark={sparks[k.key]} index={i} />)}
      </div>
      {data && (
        <p className="-mt-3 mb-6 text-[11px] text-ink-3">
          Period {data.period.start} → {data.period.end} (claims by submission date) vs {data.previous_period.start} → {data.previous_period.end}.
          Charts show the 12 months to period end. Hover a card for its formula.
        </p>
      )}

      {data && (
        <div className={`grid gap-4 lg:grid-cols-2 transition-opacity ${loading ? "opacity-60" : ""}`}>
          <Card>
            <CardHeader title="Claims submitted" subtitle="Claims per month by submission date" />
            <MonthlyBars data={data.claims_over_time} series={[{ key: "claims", label: "Claims", color: SERIES[0] }]} format={num} />
          </Card>
          <Card>
            <CardHeader title="Denial rate" subtitle="Denied (full or partial) / adjudicated claims, by submission month" />
            <TrendChart data={data.claims_over_time} series={[{ key: "denial_rate", label: "Denial rate", color: SERIES[1] }]}
              format={(v) => pct(v)} />
          </Card>
          <Card>
            <CardHeader title="Payments received" subtitle="Cash by payment month" />
            <MonthlyBars data={data.payments_over_time}
              series={[{ key: "payer_paid", label: "Payer payments", color: SERIES[0] }, { key: "patient_paid", label: "Patient payments", color: SERIES[2] }]}
              format={usdCompact} />
          </Card>
          <Card>
            <CardHeader title="Clean claim & first-pass resolution" subtitle="Front-end quality vs adjudication outcome" />
            <TrendChart data={data.claims_over_time}
              series={[{ key: "clean_claim_rate", label: "Clean claim rate", color: SERIES[2] }, { key: "first_pass_resolution_rate", label: "First-pass resolution", color: SERIES[5] }]}
              format={(v) => pct(v, 0)} />
          </Card>
          <Card>
            <CardHeader title="Outstanding AR" subtitle="Point-in-time AR at each month end" />
            <AreaTrend data={data.ar_over_time} dataKey="outstanding_ar" label="Outstanding AR" color={SERIES[0]} format={usdCompact} />
          </Card>
          <Card>
            <CardHeader title="Days in AR" subtitle="AR / average daily charges (trailing 90 days)" />
            <TrendChart data={data.ar_over_time} series={[{ key: "days_in_ar", label: "Days in AR", color: SERIES[3] }]}
              format={(v) => v.toFixed(0)} />
          </Card>
          <Card>
            <CardHeader title="Top denial reasons" subtitle="CARC codes for claims in the selected period"
              right={<Link href="/denials" className="text-xs text-accent hover:underline">All denials →</Link>} />
            <BarList format={num} color={SERIES[1]}
              rows={data.top_denial_reasons.map((r) => ({ label: `CARC ${r.carc_code}`, sublabel: titleCase(r.category), value: r.count, title: r.description }))} />
          </Card>
          <Card>
            <CardHeader title="Claim status distribution" subtitle="Claims in the selected period" />
            <BarList format={num}
              rows={data.status_distribution.map((s) => ({ label: titleCase(s.status), sublabel: `${s.share_pct}% · ${usdCompact(s.balance)} open`, value: s.count }))} />
          </Card>
          <Card className="lg:col-span-2">
            <CardHeader title="Payer performance" subtitle="Claims submitted in the selected period"
              right={<Link href="/analytics" className="text-xs text-accent hover:underline">Payer & provider analytics →</Link>} />
            <PayerTable rows={data.payers} />
          </Card>
        </div>
      )}
    </div>
  );
}
