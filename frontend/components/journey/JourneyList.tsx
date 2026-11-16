"use client";

import clsx from "clsx";
import { CalendarPlus, Hand, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Btn, MiniProgress, PHASES, STEPS } from "@/components/journey/shared";
import { Card, EmptyState, ErrorState, PageHeader, Skeleton } from "@/components/ui/primitives";
import { useApi } from "@/hooks/useApi";
import { usd } from "@/lib/format";
import { bookSample } from "@/lib/journey";
import type { EncounterList, JourneyOptions, Scorecard } from "@/types/journey";

const WHO: Record<string, string> = {
  eligibility: "Front desk", consultation: "Doctor", sign_off: "Doctor", scrub: "Coder", denial: "Biller", patient_payment: "Patient",
};

// Slide 16: the RCM scorecard, measured on the encounters that went through this pipeline.
function scoreTiles(s: Scorecard) {
  const fmt = (v: number | null, suffix = "%") => (v === null ? "—" : `${v.toFixed(1)}${suffix}`);
  const meets = (v: number | null, ok: (x: number) => boolean) => (v === null ? null : ok(v));
  return [
    { label: "Clean claim rate", value: fmt(s.clean_claim_rate), target: "95%+", ok: meets(s.clean_claim_rate, (x) => x >= 95), hint: "accepted on first submission" },
    { label: "Denial rate", value: fmt(s.denial_rate), target: "≤5%", ok: meets(s.denial_rate, (x) => x <= 5), hint: "of adjudicated service lines" },
    { label: "Days to cash", value: fmt(s.days_to_cash, " d"), target: "<40", ok: meets(s.days_to_cash, (x) => x < 40), hint: "visit to closed account (simulated)" },
    { label: "Net collection rate", value: fmt(s.net_collection_rate), target: "95%+", ok: meets(s.net_collection_rate, (x) => x >= 95), hint: "collectible dollars collected" },
    { label: "First-pass resolution", value: fmt(s.first_pass_resolution), target: "90%+", ok: meets(s.first_pass_resolution, (x) => x >= 90), hint: "paid with no rework" },
    { label: "Automated vs human", value: `${s.automated_steps} / ${s.human_actions}`, target: "Lower cost", ok: s.automated_steps > s.human_actions * 2 ? true : null, hint: "steps the AI ran / human actions" },
  ];
}

export function JourneyList() {
  const router = useRouter();
  const { data, error, loading, reload } = useApi<EncounterList>("/api/encounters");
  const opts = useApi<JourneyOptions>("/api/encounters/options");
  const [tab, setTab] = useState<"all" | "attention" | "open" | "closed">("all");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const items = (data?.items ?? []).filter((e) =>
    tab === "all" ? true : tab === "attention" ? !!e.attention : tab === "closed" ? e.stage === "closed" : e.stage !== "closed");

  const demo = async (id: string) => {
    const s = opts.data?.samples.find((x) => x.id === id);
    if (!s || !opts.data) return;
    setBusy(true);
    setErr(null);
    try {
      const enc = await bookSample(s, opts.data);
      router.push(`/journey/${enc.id}`);
    } catch (e) {
      setErr((e as Error).message);
      setBusy(false);
    }
  };

  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader eyebrow="From consultation to cash" title="Patient journeys"
        description="Every visit, from booking to a closed account. The AI runs every handoff it can; people only step in for clinical judgment, approvals and payment."
        right={<div className="flex flex-wrap gap-2">
          <select aria-label="Create a demo visit" disabled={busy || !opts.data} value="" onChange={(e) => e.target.value && demo(e.target.value)}
            className="rounded-lg border border-line bg-surface-2 px-2 py-1.5 text-xs text-ink-2">
            <option value="">{busy ? "Booking…" : "Quick demo visit…"}</option>
            {opts.data?.samples.map((s) => <option key={s.id} value={s.id}>{s.title}</option>)}
          </select>
          <Link href="/book" className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent/85">
            <CalendarPlus className="h-3.5 w-3.5" /> Book a visit</Link>
        </div>} />

      {(error || err) && <ErrorState message={error || err || ""} onRetry={reload} />}

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        {data ? scoreTiles(data.scorecard).map((t) => (
          <Card key={t.label} className="p-4">
            <p className="text-xs text-ink-3">{t.label}</p>
            <p className="tabular mt-1 text-2xl font-semibold text-ink">{t.value}</p>
            <p className="mt-1 text-[11px] text-ink-3">
              Target <span className={clsx("font-medium", t.ok === true ? "text-good" : t.ok === false ? "text-warning" : "text-ink-2")}>{t.target}</span> · {t.hint}
            </p>
          </Card>
        )) : Array.from({ length: 6 }, (_, i) => <Skeleton key={i} className="h-28 rounded-2xl" />)}
      </div>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-4 py-3">
          <div className="flex gap-1" role="tablist">
            {([["all", "All"], ["attention", `Needs a person${data ? ` (${data.scorecard.needs_attention})` : ""}`], ["open", "In progress"], ["closed", "Closed"]] as const).map(([k, label]) => (
              <button key={k} role="tab" aria-selected={tab === k} onClick={() => setTab(k)}
                className={clsx("rounded-lg px-3 py-1.5 text-xs", tab === k ? "bg-accent/15 text-ink ring-1 ring-inset ring-accent/30" : "text-ink-3 hover:text-ink")}>{label}</button>
            ))}
          </div>
          <div className="hidden items-center gap-3 text-[11px] text-ink-3 md:flex">
            {PHASES.map((p) => <span key={p.name} className="inline-flex items-center gap-1"><span className="h-2 w-2 rounded-sm" style={{ background: p.color }} />{p.name}</span>)}
          </div>
        </div>
        {loading && !data ? <div className="space-y-2 p-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-12" />)}</div>
          : items.length === 0 ? (
            data?.items.length ? <EmptyState message="No visits in this view." /> : (
              <div className="flex flex-col items-center gap-3 px-6 py-14 text-center">
                <Sparkles className="h-6 w-6 text-accent" />
                <p className="text-sm text-ink-2">No visits yet. Book one, or start a ready-made demo visit to watch the whole cycle run.</p>
                <div className="flex gap-2">
                  <Link href="/book" className="rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent/85">Book a visit</Link>
                  {opts.data?.samples[0] && <Btn busy={busy} onClick={() => demo(opts.data!.samples[0].id)}>Demo: {opts.data.samples[0].title}</Btn>}
                </div>
              </div>
            )
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[960px] text-sm">
                <thead>
                  <tr className="text-left text-[11px] text-ink-3">
                    {["Patient", "Doctor", "Visit", "Progress", "Waiting on", "Billed", "Collected", "Balance"].map((h, i) => (
                      <th key={h} className={clsx("px-4 py-2 font-medium", i >= 5 && "text-right")}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {items.map((e) => {
                    const closed = e.stage === "closed";
                    return (
                      <tr key={e.id} className="cursor-pointer border-t border-line hover:bg-white/[0.02]" onClick={() => router.push(`/journey/${e.id}`)}>
                        <td className="px-4 py-2.5"><Link href={`/journey/${e.id}`} className="font-medium text-ink hover:text-accent" onClick={(ev) => ev.stopPropagation()}>{e.patient_name}</Link>
                          <p className="font-mono text-[11px] text-ink-3">{e.id}</p></td>
                        <td className="px-4 py-2.5 text-xs text-ink-2">{e.doctor}<p className="text-ink-3">{e.payer}</p></td>
                        <td className="px-4 py-2.5 text-xs text-ink-2">{new Date(e.scheduled_at).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}
                          <p className="max-w-[200px] truncate text-ink-3">{e.visit_reason}</p></td>
                        <td className="px-4 py-2.5"><MiniProgress step={e.step} closed={closed} />
                          <p className="mt-1 text-[11px] text-ink-3">{closed ? "Closed" : `${e.step}. ${STEPS[e.step - 1]?.short}`}</p></td>
                        <td className="px-4 py-2.5 text-xs">{e.attention ? (
                          <span className="inline-flex items-center gap-1 text-warning"><Hand className="h-3 w-3" />{WHO[e.attention]}</span>
                        ) : closed ? <span className="text-good">Done</span> : <span className="text-ink-3">Autopilot</span>}</td>
                        <td className="tabular px-4 py-2.5 text-right text-xs">{usd(e.total_charge, true)}</td>
                        <td className="tabular px-4 py-2.5 text-right text-xs">{usd(e.payer_paid + e.patient_paid, true)}</td>
                        <td className="tabular px-4 py-2.5 text-right text-xs">{usd(Math.abs(e.balance) < 0.005 ? 0 : e.balance, true)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
      </Card>
    </div>
  );
}
