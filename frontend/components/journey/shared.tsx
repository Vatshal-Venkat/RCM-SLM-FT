"use client";

import clsx from "clsx";
import {
  AlertTriangle, Bot, Building2, CheckCircle2, CircleAlert, Landmark, Loader2, Network, OctagonAlert, Stethoscope,
  User, UserCog, Wrench,
} from "lucide-react";
import type { ButtonHTMLAttributes, ReactNode } from "react";

import { usd } from "@/lib/format";
import type { CoverageStatus, ServiceLine } from "@/types/journey";

// The 15-step workflow from the deck (slide 4), grouped into its three phases (slide 3).
export const STEPS: { step: number; stage: string; label: string; short: string }[] = [
  { step: 1, stage: "booked", label: "Patient books appointment", short: "Book" },
  { step: 2, stage: "registered", label: "Register patient and insurance", short: "Register" },
  { step: 3, stage: "eligibility_verified", label: "Verify eligibility and benefits", short: "Eligibility" },
  { step: 4, stage: "authorization_checked", label: "Prior authorization check", short: "Prior auth" },
  { step: 5, stage: "checked_in", label: "Check in, collect copay", short: "Check in" },
  { step: 6, stage: "in_consultation", label: "Doctor consultation (AI scribe)", short: "Consult" },
  { step: 7, stage: "documented", label: "Clinical notes in the health record", short: "Notes" },
  { step: 8, stage: "charges_captured", label: "Charge capture on superbill", short: "Charges" },
  { step: 9, stage: "coded", label: "Medical coding: diagnosis + service", short: "Coding" },
  { step: 10, stage: "claim_scrubbed", label: "Build and scrub the claim", short: "Scrub" },
  { step: 11, stage: "submitted", label: "Submit via clearinghouse", short: "Submit" },
  { step: 12, stage: "adjudicated", label: "Payer reviews (adjudication)", short: "Adjudicate" },
  { step: 13, stage: "payment_posted", label: "Insurer pays, payment posted", short: "Posted" },
  { step: 14, stage: "patient_billed", label: "Bill patient balance", short: "Bill patient" },
  { step: 15, stage: "closed", label: "Follow up and close the account", short: "Closed" },
];
export const PHASES = [
  { name: "Front end", sub: "Patient access", steps: [1, 2, 3, 4, 5], color: "var(--series-1)" },
  { name: "Mid cycle", sub: "Clinical and coding", steps: [6, 7, 8, 9], color: "var(--series-6)" },
  { name: "Back end", sub: "Claims and cash", steps: [10, 11, 12, 13, 14, 15], color: "var(--series-3)" },
];

export function Stepper({ step, attention, closed }: { step: number; attention: boolean; closed: boolean }) {
  return (
    <div className="glass overflow-x-auto rounded-2xl px-4 py-3">
      <div className="flex min-w-[640px] gap-3">
        {PHASES.map((ph) => (
          <div key={ph.name} className="flex-1" style={{ flexGrow: ph.steps.length }}>
            <div className="mb-2 flex items-baseline gap-2">
              <span className="h-2 w-2 rounded-full" style={{ background: ph.color }} aria-hidden />
              <span className="text-[11px] font-semibold uppercase tracking-wider text-ink-2">{ph.name}</span>
              <span className="text-[11px] text-ink-3">{ph.sub}</span>
            </div>
            <ol className="flex gap-1">
              {ph.steps.map((n) => {
                const s = STEPS[n - 1];
                const done = closed || n < step;
                const current = !closed && n === step;
                return (
                  <li key={n} className="min-w-0 flex-1" title={`${n}. ${s.label}`}>
                    <div className={clsx("h-1.5 rounded-full", done ? "" : current ? "" : "bg-white/[0.07]")}
                      style={done ? { background: ph.color } : current ? { background: ph.color, opacity: 0.55 } : undefined} />
                    <div className="mt-1.5 flex items-center gap-1">
                      {done ? <CheckCircle2 className="h-3 w-3 shrink-0" style={{ color: ph.color }} aria-hidden />
                        : current && attention ? <CircleAlert className="h-3 w-3 shrink-0 text-warning" aria-hidden />
                          : <span className={clsx("grid h-3 w-3 shrink-0 place-items-center rounded-full text-[8px] font-bold",
                            current ? "bg-accent text-white" : "bg-white/10 text-ink-3")}>{n}</span>}
                      <span className={clsx("truncate text-[11px]", done ? "text-ink-2" : current ? "font-medium text-ink" : "text-ink-3")}>{s.short}</span>
                    </div>
                  </li>
                );
              })}
            </ol>
          </div>
        ))}
      </div>
    </div>
  );
}

export function MiniProgress({ step, closed }: { step: number; closed: boolean }) {
  return (
    <div className="flex gap-0.5" aria-label={`Step ${step} of 15`}>
      {STEPS.map((s) => {
        const ph = PHASES.find((p) => p.steps.includes(s.step))!;
        const on = closed || s.step <= step;
        return <span key={s.step} className="h-1.5 w-2.5 rounded-sm" style={{ background: on ? ph.color : "rgba(255,255,255,0.08)" }} />;
      })}
    </div>
  );
}

export function Btn({ variant = "secondary", busy, children, className, ...rest }:
  ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" | "ghost"; busy?: boolean }) {
  return (
    <button {...rest} disabled={rest.disabled || busy}
      className={clsx("inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors disabled:opacity-45",
        variant === "primary" && "bg-accent text-white hover:bg-accent/85",
        variant === "secondary" && "bg-white/[0.06] text-ink ring-1 ring-inset ring-white/10 hover:bg-white/10",
        variant === "danger" && "bg-red-500/15 text-red-200 ring-1 ring-inset ring-red-400/30 hover:bg-red-500/25",
        variant === "ghost" && "text-ink-2 hover:bg-white/5 hover:text-ink", className)}>
      {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
      {children}
    </button>
  );
}

const COVERAGE: Record<string, { label: string; cls: string }> = {
  covered: { label: "Covered", cls: "bg-emerald-500/12 text-emerald-300 ring-emerald-400/25" },
  prior_auth_approved: { label: "Prior auth approved", cls: "bg-emerald-500/12 text-emerald-300 ring-emerald-400/25" },
  prior_auth_denied: { label: "Prior auth denied", cls: "bg-red-500/12 text-red-300 ring-red-400/25" },
  prior_auth_required: { label: "Prior auth required", cls: "bg-amber-500/12 text-amber-300 ring-amber-400/25" },
  not_covered: { label: "Not covered", cls: "bg-red-500/12 text-red-300 ring-red-400/25" },
  medical_necessity_risk: { label: "Denial risk", cls: "bg-amber-500/12 text-amber-300 ring-amber-400/25" },
};

export function coverageKey(ln: Pick<ServiceLine, "coverage_status" | "auth_status">): string {
  if (ln.coverage_status === "prior_auth_required" && ln.auth_status === "approved") return "prior_auth_approved";
  if (ln.coverage_status === "prior_auth_required" && ln.auth_status === "denied") return "prior_auth_denied";
  return ln.coverage_status;
}

export function CoverageBadge({ status, auth }: { status: CoverageStatus; auth?: string | null }) {
  const key = coverageKey({ coverage_status: status, auth_status: auth ?? null });
  const c = COVERAGE[key] ?? COVERAGE.covered;
  const Icon = key.endsWith("denied") || key === "not_covered" ? OctagonAlert : key === "covered" || key.endsWith("approved") ? CheckCircle2 : AlertTriangle;
  return (
    <span className={clsx("inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset", c.cls)}>
      <Icon className="h-3 w-3" aria-hidden /> {c.label}
    </span>
  );
}

export const DECISIONS: Record<string, string> = {
  bill_insurance: "Bill insurance",
  bill_with_abn: "Bill with ABN (GA)",
  self_pay: "Patient self-pay",
  do_not_perform: "Do not perform",
};

const ACTORS: Record<string, { icon: typeof Bot; label: string; cls: string }> = {
  ai: { icon: Bot, label: "AI", cls: "text-accent" },
  patient: { icon: User, label: "Patient", cls: "text-sky-300" },
  doctor: { icon: Stethoscope, label: "Doctor", cls: "text-violet-300" },
  front_desk: { icon: UserCog, label: "Front desk", cls: "text-teal-300" },
  coder: { icon: UserCog, label: "Biller", cls: "text-teal-300" },
  payer: { icon: Landmark, label: "Payer", cls: "text-amber-300" },
  clearinghouse: { icon: Network, label: "Clearinghouse", cls: "text-orange-300" },
  system: { icon: Wrench, label: "System", cls: "text-ink-3" },
};

export function ActorTag({ actor }: { actor: string }) {
  const a = ACTORS[actor] ?? { icon: Building2, label: actor, cls: "text-ink-3" };
  const Icon = a.icon;
  return (
    <span className={clsx("inline-flex items-center gap-1 text-[11px] font-medium", a.cls)}>
      <Icon className="h-3 w-3" aria-hidden /> {a.label}
    </span>
  );
}

export function Section({ step, title, subtitle, right, children, id }: {
  step?: string; title: string; subtitle?: ReactNode; right?: ReactNode; children: ReactNode; id?: string;
}) {
  return (
    <section id={id} className="glass scroll-mt-6 rounded-2xl animate-fade-up">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-3.5">
        <div className="min-w-0">
          {step && <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-accent-2">{step}</p>}
          <h2 className="text-sm font-semibold text-ink">{title}</h2>
          {subtitle && <p className="mt-0.5 text-xs text-ink-3">{subtitle}</p>}
        </div>
        {right}
      </div>
      <div className="px-5 py-4">{children}</div>
    </section>
  );
}

export function Stat({ label, value, hint, tone }: { label: string; value: ReactNode; hint?: string; tone?: "good" | "warn" | "bad" }) {
  return (
    <div className="rounded-xl border border-line bg-white/[0.02] px-3 py-2.5">
      <p className="text-[11px] text-ink-3">{label}</p>
      <p className={clsx("tabular mt-0.5 text-base font-semibold",
        tone === "good" ? "text-good" : tone === "warn" ? "text-warning" : tone === "bad" ? "text-critical" : "text-ink")}>{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-ink-3">{hint}</p>}
    </div>
  );
}

export function CheckIcon({ status }: { status: string }) {
  if (status === "pass") return <CheckCircle2 className="h-4 w-4 shrink-0 text-good" aria-label="Pass" />;
  if (status === "fixed") return <Wrench className="h-4 w-4 shrink-0 text-accent-2" aria-label="Auto-fixed" />;
  if (status === "warn") return <AlertTriangle className="h-4 w-4 shrink-0 text-warning" aria-label="Warning" />;
  return <OctagonAlert className="h-4 w-4 shrink-0 text-critical" aria-label="Fail" />;
}

/** Slide 14: billed charge -> contract write-off -> allowed -> insurer pays -> patient owes. */
export function Waterfall({ billed, writeoff, allowed, insurer, patient }: {
  billed: number; writeoff: number; allowed: number; insurer: number; patient: number;
}) {
  const max = Math.max(billed, 1);
  const rows = [
    { label: "Billed charge", value: billed, offset: 0, color: "var(--series-1)" },
    { label: "Contract write-off", value: -writeoff, offset: allowed, color: "var(--axis)" },
    { label: "Allowed amount", value: allowed, offset: 0, color: "var(--series-6)" },
    { label: "Insurer pays", value: insurer, offset: 0, color: "var(--series-3)" },
    { label: "Patient owes", value: patient, offset: insurer, color: "var(--series-4)" },
  ];
  return (
    <div className="space-y-2">
      {rows.map((r) => (
        <div key={r.label} className="grid grid-cols-[120px_1fr_80px] items-center gap-3 text-xs">
          <span className="text-ink-3">{r.label}</span>
          <div className="relative h-5 rounded bg-white/[0.03]">
            <div className="absolute inset-y-0 rounded" style={{
              left: `${(r.offset / max) * 100}%`, width: `${(Math.abs(r.value) / max) * 100}%`, background: r.color,
            }} />
          </div>
          <span className="tabular text-right font-medium text-ink">{r.value < 0 ? "−" : ""}{usd(Math.abs(r.value), true)}</span>
        </div>
      ))}
    </div>
  );
}

export function Pre({ children }: { children: string }) {
  return <pre className="max-h-72 overflow-auto rounded-xl border border-line bg-black/30 p-3 font-mono text-[11px] leading-relaxed text-ink-2">{children}</pre>;
}

export function Details({ summary, children }: { summary: ReactNode; children: ReactNode }) {
  return (
    <details className="group rounded-xl border border-line bg-white/[0.02]">
      <summary className="cursor-pointer select-none px-3 py-2 text-xs text-ink-2 hover:text-ink">{summary}</summary>
      <div className="px-3 pb-3">{children}</div>
    </details>
  );
}
