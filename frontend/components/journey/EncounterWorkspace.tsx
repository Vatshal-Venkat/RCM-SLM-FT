"use client";

import clsx from "clsx";
import { ArrowLeft, ArrowRight, Bot, CalendarClock, CircleAlert, FastForward, Hand, ListOrdered, Stethoscope, UserRound } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

import { CodingPanel, NotePanel } from "@/components/journey/ClinicalPanels";
import { AdjudicationPanel, AppealPanel, BillingPanel, ClaimPanel, FrontDeskPanel, PaymentPanel } from "@/components/journey/RevenuePanels";
import { ScribePanel } from "@/components/journey/ScribePanel";
import { ActorTag, Btn, Details, STEPS, Section, Stepper } from "@/components/journey/shared";
import { ErrorState, Skeleton } from "@/components/ui/primitives";
import { useApi } from "@/hooks/useApi";
import { apiPost } from "@/lib/api";
import { usd } from "@/lib/format";
import type { BillingDecision, EncounterDetail, JourneyOptions, Utterance } from "@/types/journey";

const ATTENTION: Record<string, { who: string; what: string; anchor: string }> = {
  eligibility: { who: "Front desk", what: "Fix the insurance details and re-verify eligibility", anchor: "front" },
  consultation: { who: "Doctor", what: "Hold the visit with the AI scribe listening, then end the visit", anchor: "consultation" },
  sign_off: { who: "Doctor", what: "Review the AI-drafted note, codes and coverage, then sign", anchor: "coding" },
  scrub: { who: "Coder", what: "Fix the claim error the scrubber could not correct", anchor: "claim" },
  denial: { who: "Biller", what: "Approve the AI-drafted appeal or accept the denial", anchor: "denial" },
  patient_payment: { who: "Patient", what: "Pay the remaining balance", anchor: "billing" },
};

export function EncounterRoute() {
  const { id } = useParams<{ id: string }>();
  return <EncounterWorkspace encounterId={decodeURIComponent(id)} />;
}

export function EncounterWorkspace({ encounterId }: { encounterId: string }) {
  const { data, error, loading, reload } = useApi<EncounterDetail>(`/api/encounters/${encodeURIComponent(encounterId)}`);
  const opts = useApi<JourneyOptions>("/api/encounters/options");
  const [live, setLive] = useState<EncounterDetail | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [newestFirst, setNewestFirst] = useState(true);
  const enc = live && live.id === encounterId ? live : data;

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 6000);
    return () => clearTimeout(t);
  }, [toast]);

  const act = async (key: string, path: string, body?: unknown): Promise<EncounterDetail | null> => {
    setBusy(key);
    setActionError(null);
    try {
      const next = await apiPost<EncounterDetail>(`/api/encounters/${encounterId}${path}`, body);
      setLive(next);
      const anchor = next.attention ? ATTENTION[next.attention]?.anchor : null;
      if (anchor && anchor !== "consultation") setTimeout(() => document.getElementById(anchor)?.scrollIntoView({ behavior: "smooth", block: "start" }), 120);
      return next;
    } catch (e) {
      setActionError((e as Error).message);
      return null;
    } finally {
      setBusy(null);
    }
  };

  const runAutopilot = async () => {
    const next = await act("autopilot", "/autopilot");
    const steps = next?.result?.steps?.length ?? 0;
    if (next) setToast(next.stage === "closed" ? `Autopilot ran ${steps} step${steps === 1 ? "" : "s"}: account closed.`
      : `Autopilot ran ${steps} step${steps === 1 ? "" : "s"}${next.attention ? `; waiting for ${ATTENTION[next.attention]?.who.toLowerCase()}.` : "."}`);
  };

  if (error) return <div className="mx-auto max-w-[1400px] space-y-4"><BackLink /><ErrorState message={error} onRetry={reload} /></div>;
  if (loading && !enc) {
    return <div className="mx-auto max-w-[1400px] space-y-4"><BackLink /><Skeleton className="h-24 rounded-2xl" /><Skeleton className="h-16 rounded-2xl" /><Skeleton className="h-96 rounded-2xl" /></div>;
  }
  if (!enc) return null;

  const closed = enc.stage === "closed";
  const att = enc.attention ? ATTENTION[enc.attention] : null;
  const showScribe = enc.stage === "checked_in" || enc.stage === "in_consultation";
  const events = newestFirst ? [...enc.events].reverse() : enc.events;
  const when = new Date(enc.scheduled_at);

  return (
    <div className="mx-auto max-w-[1400px] space-y-4">
      <BackLink />
      {/* Header */}
      <div className="flex flex-wrap items-end justify-between gap-4 animate-fade-up">
        <div className="min-w-0">
          <p className="text-xs font-medium uppercase tracking-[0.18em] text-accent-2">Patient journey · {enc.id}</p>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink md:text-3xl">{enc.patient_name}</h1>
          <p className="mt-1.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-sm text-ink-2">
            <span className="inline-flex items-center gap-1.5"><Stethoscope className="h-3.5 w-3.5 text-ink-3" />{enc.doctor} · {enc.specialty}</span>
            <span className="inline-flex items-center gap-1.5"><CalendarClock className="h-3.5 w-3.5 text-ink-3" />
              {when.toLocaleString("en-US", { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}</span>
            <span className="inline-flex items-center gap-1.5"><UserRound className="h-3.5 w-3.5 text-ink-3" />{enc.insurance.payer} · {enc.insurance.member_id}</span>
          </p>
          <p className="mt-1 text-xs text-ink-3">Reason for visit: {enc.visit_reason}</p>
        </div>
        <div className="flex gap-2">
          <Btn busy={busy === "advance"} disabled={!!enc.attention || closed || !!busy} onClick={() => act("advance", "/advance")}
            title="Run only the next step">Next step <ArrowRight className="h-3.5 w-3.5" /></Btn>
          <Btn variant="primary" busy={busy === "autopilot"} disabled={!!enc.attention || closed || !!busy} onClick={runAutopilot}
            title="Run every step that does not need a person">
            <FastForward className="h-3.5 w-3.5" /> Run autopilot</Btn>
        </div>
      </div>

      <Stepper step={enc.step} attention={!!enc.attention} closed={closed} />

      {att && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-amber-400/30 bg-amber-500/[0.07] px-4 py-3 animate-fade-up" role="status">
          <div className="flex min-w-0 items-start gap-2.5">
            <Hand className="mt-0.5 h-4 w-4 shrink-0 text-warning" aria-hidden />
            <div className="min-w-0">
              <p className="text-sm font-medium text-ink">Waiting for the {att.who.toLowerCase()}: {att.what}</p>
              {enc.attention_detail && <p className="text-xs text-ink-2">{enc.attention_detail}</p>}
            </div>
          </div>
          <a href={`#${att.anchor}`} className="rounded-lg bg-white/[0.06] px-3 py-1.5 text-xs text-ink ring-1 ring-inset ring-white/10 hover:bg-white/10">Go to step</a>
        </div>
      )}
      {!att && !closed && (
        <div className="flex items-center gap-2.5 rounded-2xl border border-line bg-white/[0.02] px-4 py-3 text-sm text-ink-2">
          <Bot className="h-4 w-4 text-accent" aria-hidden />
          Next: <span className="font-medium text-ink">{STEPS[Math.min(enc.step, 14)].label}</span>. Nothing needs a person right now; run the autopilot.
        </div>
      )}
      {actionError && <ErrorState message={actionError} />}
      {toast && <div className="fixed bottom-5 right-5 z-50 rounded-xl border border-line bg-surface-2 px-4 py-2.5 text-sm text-ink shadow-xl animate-fade-up" role="status">{toast}</div>}

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0 space-y-4">
          <FrontDeskPanel enc={enc} plans={opts.data?.plans ?? []} busy={busy === "fix"}
            onFix={async (member_id, payer_id) => { await act("fix", "/registration", { member_id, payer_id }); }} />

          {enc.stage === "authorization_checked" && (
            <Section step="Step 5 · Check in" title="Patient arrives"
              subtitle="Checking in collects the copay from the eligibility response and opens the exam room for the AI scribe.">
              <Btn variant="primary" busy={busy === "advance"} onClick={() => act("advance", "/advance")}>Check in patient</Btn>
            </Section>
          )}

          {showScribe && (
            <ScribePanel key={enc.id} initial={enc.transcript} samples={opts.data?.samples ?? []} visitReason={enc.visit_reason}
              busy={busy === "scribe" || busy === "save"}
              onSave={async (u: Utterance[]) => { await act("save", "/transcript", { utterances: u }); setToast("Transcript saved."); }}
              onFinish={async (u: Utterance[]) => {
                const saved = await act("scribe", "/transcript", { utterances: u });
                if (saved) await act("scribe", "/scribe");
              }} />
          )}
          {!showScribe && enc.transcript.length > 0 && (
            <Details summary={<span className="inline-flex items-center gap-1.5"><ListOrdered className="h-3.5 w-3.5" /> Consultation transcript ({enc.transcript.length} utterances, captured by the AI scribe)</span>}>
              <ul className="space-y-1.5 text-sm">
                {enc.transcript.map((u, i) => (
                  <li key={i}><span className={clsx("mr-1.5 text-[11px] font-semibold uppercase", u.speaker === "doctor" ? "text-violet-300" : "text-sky-300")}>{u.speaker}</span>
                    <span className="text-ink-2">{u.text}</span></li>
                ))}
              </ul>
            </Details>
          )}

          {enc.note && <NotePanel note={enc.note} signed={enc.signed} doctor={enc.doctor} />}
          {enc.coding && (
            <CodingPanel enc={enc} busy={busy === "coding" || busy === "sign"}
              onSave={async (diagnoses: string[], lines: { code: string; modifier: string | null; units: number; billing_decision: BillingDecision | null }[]) =>
                (await act("coding", "/coding", { diagnoses, lines })) !== null}
              onSign={async () => {
                const signed = await act("sign", "/sign");
                if (signed) await runAutopilot();
              }} />
          )}
          <ClaimPanel enc={enc} />
          <AdjudicationPanel enc={enc} />
          <PaymentPanel enc={enc} />
          <AppealPanel enc={enc} busy={busy === "denial"} onDecide={async (action) => {
            const r = await act("denial", "/denial", { action });
            if (r) await runAutopilot();
          }} />
          <BillingPanel enc={enc} busy={busy === "pay"} onPay={async (amount) => {
            const r = await act("pay", "/patient-payment", amount ? { amount } : {});
            if (r && !r.attention) await runAutopilot();
          }} />
        </div>

        {/* Side column */}
        <aside className="space-y-4 xl:sticky xl:top-6 xl:self-start">
          <div className="glass rounded-2xl p-4">
            <h2 className="text-sm font-semibold text-ink">Money</h2>
            <dl className="mt-3 space-y-1.5 text-sm">
              {[
                ["Billed charges", enc.totals.total_charge],
                ["Insurance paid", enc.totals.payer_paid],
                ["Patient paid", enc.totals.patient_paid],
                ["Adjustments & write-offs", enc.totals.adjustments],
              ].map(([k, v]) => (
                <div key={k as string} className="flex justify-between gap-2"><dt className="text-ink-3">{k}</dt><dd className="tabular text-ink">{usd(v as number, true)}</dd></div>
              ))}
              <div className="flex justify-between gap-2 border-t border-line pt-1.5"><dt className="font-medium text-ink-2">Open balance</dt>
                <dd className={clsx("tabular font-semibold", Math.abs(enc.totals.balance) < 0.005 ? "text-good" : "text-ink")}>{usd(Math.abs(enc.totals.balance) < 0.005 ? 0 : enc.totals.balance, true)}</dd></div>
            </dl>
            <div className="mt-4 grid grid-cols-3 gap-2 text-center">
              <div className="rounded-lg bg-white/[0.03] p-2"><p className="tabular text-lg font-semibold text-accent">{enc.metrics.automated_steps}</p><p className="text-[10px] text-ink-3">automated steps</p></div>
              <div className="rounded-lg bg-white/[0.03] p-2"><p className="tabular text-lg font-semibold text-ink">{enc.metrics.human_actions}</p><p className="text-[10px] text-ink-3">human actions</p></div>
              <div className="rounded-lg bg-white/[0.03] p-2"><p className="tabular text-lg font-semibold text-ink">{enc.metrics.sim_day}</p><p className="text-[10px] text-ink-3">days since visit (sim.)</p></div>
            </div>
          </div>

          <div className="glass rounded-2xl">
            <div className="flex items-center justify-between border-b border-line px-4 py-3">
              <h2 className="text-sm font-semibold text-ink">Audit trail</h2>
              <button onClick={() => setNewestFirst(!newestFirst)} className="text-[11px] text-ink-3 hover:text-ink">{newestFirst ? "Newest first" : "Oldest first"}</button>
            </div>
            <ol className="max-h-[70vh] space-y-3 overflow-y-auto px-4 py-3">
              {events.map((ev) => (
                <li key={ev.id} className="relative pl-4">
                  <span className={clsx("absolute left-0 top-1.5 h-2 w-2 rounded-full",
                    ev.level === "success" ? "bg-good" : ev.level === "warning" ? "bg-warning" : ev.level === "error" ? "bg-critical" : "bg-ink-3")} aria-hidden />
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                    <span className="rounded bg-white/[0.06] px-1 text-[10px] font-semibold text-ink-3" title={STEPS[ev.step - 1]?.label}>Step {ev.step}</span>
                    <ActorTag actor={ev.actor} />
                    {!ev.automated && <span className="inline-flex items-center gap-0.5 text-[10px] text-warning"><CircleAlert className="h-2.5 w-2.5" />human</span>}
                    <span className="ml-auto text-[10px] text-ink-3">day {ev.sim_day}</span>
                  </div>
                  <p className="mt-0.5 text-xs font-medium text-ink">{ev.title}</p>
                  {ev.detail && <p className="text-[11px] leading-snug text-ink-3">{ev.detail}</p>}
                </li>
              ))}
            </ol>
          </div>
        </aside>
      </div>
    </div>
  );
}

function BackLink() {
  return (
    <Link href="/journey" className="inline-flex items-center gap-1.5 text-xs text-ink-3 hover:text-ink">
      <ArrowLeft className="h-3.5 w-3.5" /> All patient journeys
    </Link>
  );
}
