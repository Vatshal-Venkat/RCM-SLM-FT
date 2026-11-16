"use client";

import clsx from "clsx";
import { CalendarPlus, CheckCircle2, Sparkles } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useSyncExternalStore } from "react";

import { Btn, PHASES, STEPS } from "@/components/journey/shared";
import { Card, ErrorState, PageHeader, Skeleton } from "@/components/ui/primitives";
import { useApi } from "@/hooks/useApi";
import { apiPost, toQuery } from "@/lib/api";
import { usd } from "@/lib/format";
import { bookSample, isoDay, nextBusinessDay } from "@/lib/journey";
import type { EncounterDetail, JourneyOptions, Slots } from "@/types/journey";

const STATES = ["OH", "PA", "MI", "IN", "NY"];
const noopSubscribe = () => () => {};
const field = "mt-1 block w-full rounded-lg border border-line bg-surface-2 px-3 py-2 text-sm text-ink placeholder:text-ink-3";

export function BookingForm() {
  const router = useRouter();
  const opts = useApi<JourneyOptions>("/api/encounters/options");
  const [form, setF] = useState({
    patient_name: "", birth_year: "1985", sex: "F", state: "OH", payer_id: "PYR-NWH", member_id: "",
    doctor_id: "DR-01", day: "", time: "", visit_reason: "", new_patient: false,
  });
  // The clock is read on the client only (the prerendered shell has no date), so the shell stays static.
  const today = useSyncExternalStore(noopSubscribe, () => isoDay(new Date()), () => "");
  const f = { ...form, day: form.day || (today ? nextBusinessDay(new Date(`${today}T12:00:00`)) : "") };
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const slots = useApi<Slots>(f.doctor_id && f.day ? `/api/encounters/slots${toQuery({ doctor_id: f.doctor_id, day: f.day })}` : null);
  const set = (patch: Partial<typeof form>) => setF((x) => ({ ...x, ...patch }));
  const plan = opts.data?.plans.find((p) => p.payer_id === f.payer_id);
  const doctor = opts.data?.doctors.find((d) => d.id === f.doctor_id);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setErr(null);
    try {
      const enc = await apiPost<EncounterDetail>("/api/encounters", {
        patient_name: f.patient_name.trim(), birth_year: Number(f.birth_year), sex: f.sex, state: f.state, payer_id: f.payer_id,
        member_id: f.member_id.trim(), doctor_id: f.doctor_id, scheduled_at: `${f.day}T${f.time}:00`,
        visit_reason: f.visit_reason.trim(), new_patient: f.new_patient,
      });
      router.push(`/journey/${enc.id}`);
    } catch (ex) {
      setErr((ex as Error).message);
      setBusy(false);
      slots.reload();
    }
  };

  const demo = async (id: string) => {
    const s = opts.data?.samples.find((x) => x.id === id);
    if (!s || !opts.data) return;
    setBusy(true);
    setErr(null);
    try {
      const enc = await bookSample(s, opts.data);
      router.push(`/journey/${enc.id}`);
    } catch (ex) {
      setErr((ex as Error).message);
      setBusy(false);
    }
  };

  const ready = f.patient_name.trim().length >= 2 && f.member_id && f.time && f.visit_reason.trim().length >= 2;

  return (
    <div className="mx-auto max-w-[1200px]">
      <PageHeader eyebrow="Step 1 · Patient access" title="Book a visit"
        description="Booking starts the revenue cycle. Registration, the eligibility check (270/271) and the prior-authorization check run the moment you book, so problems surface before the patient walks in." />
      {opts.error && <ErrorState message={opts.error} onRetry={opts.reload} />}
      {!opts.data ? <Skeleton className="h-96 rounded-2xl" /> : (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
          <Card className="p-5">
            <form onSubmit={submit} className="space-y-6">
              <fieldset className="grid gap-4 sm:grid-cols-2">
                <legend className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-3">Patient</legend>
                <label className="text-xs text-ink-3 sm:col-span-2">Full name
                  <input className={field} value={f.patient_name} maxLength={80} required autoComplete="off" placeholder="Demo patient name"
                    onChange={(e) => set({ patient_name: e.target.value.replace(/[^A-Za-z .'\-]/g, "") })} /></label>
                <label className="text-xs text-ink-3">Birth year
                  <input className={field} inputMode="numeric" value={f.birth_year} maxLength={4} required
                    onChange={(e) => set({ birth_year: e.target.value.replace(/\D/g, "") })} /></label>
                <div className="grid grid-cols-2 gap-3">
                  <label className="text-xs text-ink-3">Sex
                    <select className={field} value={f.sex} onChange={(e) => set({ sex: e.target.value })}><option value="F">Female</option><option value="M">Male</option></select></label>
                  <label className="text-xs text-ink-3">State
                    <select className={field} value={f.state} onChange={(e) => set({ state: e.target.value })}>{STATES.map((s) => <option key={s}>{s}</option>)}</select></label>
                </div>
                <label className="flex items-center gap-2 text-sm text-ink-2 sm:col-span-2">
                  <input type="checkbox" checked={f.new_patient} onChange={(e) => set({ new_patient: e.target.checked })} className="h-4 w-4 accent-[var(--accent)]" />
                  New patient (first visit with this practice)</label>
              </fieldset>

              <fieldset className="grid gap-4 sm:grid-cols-2">
                <legend className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-3">Insurance</legend>
                <label className="text-xs text-ink-3">Plan
                  <select className={field} value={f.payer_id} onChange={(e) => set({ payer_id: e.target.value, member_id: "" })}>
                    {opts.data.plans.map((p) => <option key={p.payer_id} value={p.payer_id}>{p.payer} · {p.plan_name}</option>)}
                  </select></label>
                <label className="text-xs text-ink-3">Member ID (from the insurance card)
                  <input className={clsx(field, "font-mono")} value={f.member_id} maxLength={20} required placeholder={plan?.member_id_example}
                    onChange={(e) => set({ member_id: e.target.value.toUpperCase().replace(/[^A-Z0-9]/g, "") })} /></label>
                {plan && (
                  <p className="text-[11px] text-ink-3 sm:col-span-2">
                    {plan.plan_name}: copay {usd(plan.copay_pcp)} primary care / {usd(plan.copay_specialist)} specialist, deductible {usd(plan.deductible)}, coinsurance {plan.coinsurance_pct}%.{" "}
                    <button type="button" className="text-accent hover:underline" onClick={() => set({ member_id: plan.member_id_example })}>Use example card {plan.member_id_example}</button>.
                    {" "}A member ID ending in 0000 simulates inactive coverage.
                  </p>
                )}
              </fieldset>

              <fieldset className="grid gap-4 sm:grid-cols-2">
                <legend className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-3">Visit</legend>
                <label className="text-xs text-ink-3">Doctor
                  <select className={field} value={f.doctor_id} onChange={(e) => set({ doctor_id: e.target.value, time: "" })}>
                    {opts.data.doctors.map((d) => <option key={d.id} value={d.id}>{d.name} · {d.specialty}</option>)}
                  </select>
                  {doctor && <span className="mt-1 block text-[11px]">{doctor.provider}</span>}</label>
                <label className="text-xs text-ink-3">Date
                  <input type="date" className={field} value={f.day} min={today}
                    onChange={(e) => set({ day: e.target.value, time: "" })} /></label>
                <div className="sm:col-span-2">
                  <p className="text-xs text-ink-3">Time</p>
                  {slots.data?.weekend ? <p className="mt-1 text-xs text-warning">The clinic is closed on weekends.</p> : (
                    <div className="mt-1.5 flex flex-wrap gap-1.5" role="radiogroup" aria-label="Appointment time">
                      {(slots.data?.slots ?? []).map((s) => (
                        <button key={s.time} type="button" role="radio" aria-checked={f.time === s.time} disabled={!s.available} onClick={() => set({ time: s.time })}
                          className={clsx("rounded-lg px-2.5 py-1 text-xs tabular ring-1 ring-inset transition-colors disabled:cursor-not-allowed disabled:opacity-30",
                            f.time === s.time ? "bg-accent text-white ring-accent" : "bg-white/[0.03] text-ink-2 ring-white/10 hover:bg-white/10")}>{s.time}</button>
                      ))}
                    </div>
                  )}
                </div>
                <label className="text-xs text-ink-3 sm:col-span-2">Reason for visit
                  <input className={field} value={f.visit_reason} maxLength={200} required placeholder="e.g. Sore throat and fever"
                    onChange={(e) => set({ visit_reason: e.target.value })} /></label>
              </fieldset>

              {err && <ErrorState message={err} />}
              <div className="flex justify-end">
                <Btn type="submit" variant="primary" busy={busy} disabled={!ready} className="px-4 py-2 text-sm">
                  <CalendarPlus className="h-4 w-4" /> Book and verify insurance</Btn>
              </div>
            </form>
          </Card>

          <div className="space-y-4">
            <Card className="p-4">
              <h2 className="flex items-center gap-1.5 text-sm font-semibold text-ink"><Sparkles className="h-4 w-4 text-accent" /> Try a ready-made visit</h2>
              <p className="mt-1 text-xs text-ink-3">Books a demo patient in the doctor&rsquo;s next free slot. Each one exercises a different branch of the cycle.</p>
              <ul className="mt-3 space-y-2">
                {opts.data.samples.map((s) => (
                  <li key={s.id}>
                    <button disabled={busy} onClick={() => demo(s.id)}
                      className="w-full rounded-xl border border-line bg-white/[0.02] p-2.5 text-left transition-colors hover:border-accent/40 hover:bg-accent/5 disabled:opacity-50">
                      <p className="text-xs font-medium text-ink">{s.title}</p>
                      <p className="mt-0.5 text-[11px] leading-snug text-ink-3">{s.summary}</p>
                    </button>
                  </li>
                ))}
              </ul>
            </Card>
            <Card className="p-4">
              <h2 className="text-sm font-semibold text-ink">What runs automatically</h2>
              <ol className="mt-2 space-y-1.5 text-xs">
                {STEPS.slice(0, 4).map((s) => (
                  <li key={s.step} className="flex items-center gap-2 text-ink-2">
                    <CheckCircle2 className="h-3.5 w-3.5" style={{ color: PHASES[0].color }} /> {s.step}. {s.label}
                  </li>
                ))}
              </ol>
              <p className="mt-2 text-[11px] text-ink-3">Then the doctor holds the visit with the AI scribe, signs, and the autopilot takes the claim to cash.</p>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
