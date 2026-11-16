"use client";

import clsx from "clsx";
import { CreditCard, FileWarning, Gavel, Send, XCircle } from "lucide-react";
import { useState } from "react";

import { Btn, CheckIcon, Details, Pre, Section, Stat, Waterfall } from "@/components/journey/shared";
import { Pill } from "@/components/ui/primitives";
import { dateLabel, titleCase, usd } from "@/lib/format";
import type { EncounterDetail, PlanOption } from "@/types/journey";

// --------------------------------------------------------------------------- steps 2-5

export function FrontDeskPanel({ enc, plans, onFix, busy }: {
  enc: EncounterDetail; plans: PlanOption[]; onFix: (memberId: string, payerId: string) => Promise<void>; busy: boolean;
}) {
  const e = enc.eligibility;
  const [member, setMember] = useState(enc.insurance.member_id);
  const [payer, setPayer] = useState(enc.insurance.payer_id);
  const example = plans.find((p) => p.payer_id === payer)?.member_id_example;
  const pa = enc.checkin?.planned_auth;
  return (
    <Section id="front" step="Steps 2-5 · Front end" title="Registration, eligibility and check-in"
      subtitle="Many denials are born at the front desk. These checks run automatically the moment the visit is booked.">
      {e && (e.active ? (
        <div className="grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
          <Stat label="Plan" value={<span className="text-sm">{e.plan_name}</span>} hint={`${e.payer} · active on ${dateLabel(e.service_date)}`} tone="good" />
          <Stat label={`Copay (${e.copay_type})`} value={usd(e.copay ?? 0, true)} hint={enc.checkin?.copay_collected !== undefined ? `Collected at check-in: ${usd(enc.checkin.copay_collected, true)}` : "Collected at check-in"} />
          <Stat label="Deductible remaining" value={usd(e.deductible_remaining ?? 0, true)} hint={`of ${usd(e.deductible ?? 0)} · met ${usd(e.deductible_met ?? 0)}`} />
          <Stat label="Coinsurance" value={`${e.coinsurance_pct ?? 0}%`} hint={`270/271 trace ${e.trace_number}`} />
        </div>
      ) : (
        <div className="rounded-xl border border-red-400/25 bg-red-500/5 p-4">
          <p className="flex items-center gap-2 text-sm font-medium text-red-200"><XCircle className="h-4 w-4" /> {e.error} ({e.error_code})</p>
          <p className="mt-1 text-xs text-ink-2">{e.message}</p>
          {enc.attention === "eligibility" && (
            <form className="mt-3 flex flex-wrap items-end gap-2" onSubmit={(ev) => { ev.preventDefault(); void onFix(member, payer); }}>
              <label className="text-xs text-ink-3">Insurance
                <select value={payer} onChange={(ev) => setPayer(ev.target.value)} className="mt-1 block rounded-lg border border-line bg-surface-2 px-2 py-1.5 text-sm text-ink">
                  {plans.map((p) => <option key={p.payer_id} value={p.payer_id}>{p.payer} ({p.plan_name})</option>)}
                </select></label>
              <label className="text-xs text-ink-3">Member ID
                <input value={member} onChange={(ev) => setMember(ev.target.value.toUpperCase().replace(/[^A-Z0-9]/g, ""))} maxLength={20}
                  className="mt-1 block w-40 rounded-lg border border-line bg-surface-2 px-2 py-1.5 font-mono text-sm text-ink" /></label>
              <Btn type="submit" variant="primary" busy={busy}>Re-verify eligibility</Btn>
              {example && <button type="button" className="text-xs text-accent hover:underline" onClick={() => setMember(example)}>Use card example {example}</button>}
            </form>
          )}
        </div>
      ))}
      {pa && <p className="mt-3 text-xs text-ink-3"><span className="text-ink-2">Prior authorization (step 4):</span> {pa.message}</p>}
    </Section>
  );
}

// --------------------------------------------------------------------------- steps 10-11

export function ClaimPanel({ enc }: { enc: EncounterDetail }) {
  const s = enc.scrub;
  if (!s) return null;
  return (
    <Section id="claim" step="Steps 10-11 · Build, scrub and submit" title={s.claim_form ? `Claim ${s.claim_form} / ${s.transaction}` : "Claim"}
      subtitle={s.note ?? `${s.billed_lines} lines · ${usd(s.total_billed, true)} billed. The scrubber catches errors before the payer does.`}
      right={s.checks.length ? <Pill tone={s.clean ? "good" : "critical"}>{s.clean ? "Clean claim" : "Errors"}</Pill> : null}>
      {s.checks.length > 0 && (
        <ul className="space-y-2">
          {s.checks.map((c) => (
            <li key={c.check} className="flex gap-2.5">
              <CheckIcon status={c.status} />
              <div className="min-w-0"><p className="text-sm text-ink">{c.check} {c.status === "fixed" && <span className="text-xs text-accent-2">auto-corrected</span>}</p>
                <p className="text-xs text-ink-3">{c.detail}</p></div>
            </li>
          ))}
        </ul>
      )}
      {enc.clearinghouse.length > 0 && (
        <div className="mt-5 space-y-3">
          <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-3">Clearinghouse round-trips</h3>
          {enc.clearinghouse.map((sub) => (
            <div key={sub.attempt} className="rounded-xl border border-line bg-white/[0.02] p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium text-ink">Submission {sub.attempt} <span className="font-mono text-xs text-ink-3">{sub.claim_ref}</span></p>
                <Pill tone={sub.ack_277ca.status === "accepted" ? "good" : "critical"}>277CA {sub.ack_277ca.status}</Pill>
              </div>
              <ol className="mt-2 grid gap-2 sm:grid-cols-2 2xl:grid-cols-4">
                {sub.steps.map((st, i) => (
                  <li key={st.step} className="flex gap-2 text-xs">
                    <CheckIcon status={st.status} />
                    <div><p className="font-medium text-ink-2">{i + 1} · {st.step}</p><p className="text-ink-3">{st.detail}</p></div>
                  </li>
                ))}
              </ol>
              {sub.ack_277ca.auto_fix && <p className="mt-2 text-xs text-accent-2">Fix applied before resubmitting: {sub.ack_277ca.auto_fix}</p>}
              <div className="mt-2"><Details summary="View the X12 837 sent (simplified)"><Pre>{sub.x12_837}</Pre></Details></div>
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

// --------------------------------------------------------------------------- step 12

export function AdjudicationPanel({ enc }: { enc: EncounterDetail }) {
  const a = enc.adjudication;
  if (!a) return null;
  return (
    <Section id="adjudication" step="Step 12 · Payer adjudication" title="Five gates decide whether the claim pays"
      right={a.outcome ? <Pill tone={a.outcome === "paid" ? "good" : a.outcome === "denied" ? "critical" : "warning"}>{titleCase(a.outcome)}</Pill>
        : a.pended ? <Pill tone="warning">Pended</Pill> : null}>
      {a.pended && (
        <p className="mb-3 flex items-start gap-2 rounded-xl border border-amber-400/25 bg-amber-500/5 p-3 text-xs text-ink-2">
          <FileWarning className="h-4 w-4 shrink-0 text-warning" />
          <span>{a.pend_reason}. {a.records_sent ? "The AI attached the signed visit note and orders (275) automatically." : "Waiting to send records."}</span>
        </p>
      )}
      {a.gates && (
        <ol className="grid gap-2 sm:grid-cols-2 2xl:grid-cols-5">
          {a.gates.map((g, i) => (
            <li key={g.gate} className={clsx("rounded-xl border p-3", g.status === "pass" ? "border-emerald-400/20 bg-emerald-500/5" : "border-red-400/25 bg-red-500/5")}>
              <div className="flex items-center gap-1.5"><CheckIcon status={g.status} /><span className="text-xs font-medium text-ink">{i + 1} · {g.gate}</span></div>
              <p className="mt-1 text-[11px] leading-snug text-ink-3">{g.detail}</p>
            </li>
          ))}
        </ol>
      )}
    </Section>
  );
}

// --------------------------------------------------------------------------- step 13

export function PaymentPanel({ enc }: { enc: EncounterDetail }) {
  if (!enc.remittance.length) return null;
  const billedLines = enc.lines.filter((l) => l.billing_decision === "bill_insurance" || l.billing_decision === "bill_with_abn");
  const billed = billedLines.reduce((s, l) => s + l.charge * l.units, 0);
  const allowed = billedLines.reduce((s, l) => s + (l.line_status === "paid" || l.carc === "PR-50" ? l.allowed : 0), 0);
  const insurer = billedLines.reduce((s, l) => s + l.payer_paid, 0);
  const patient = billedLines.reduce((s, l) => s + l.patient_resp, 0);
  return (
    <Section id="payment" step="Step 13 · Insurance payout and payment posting" title="Following the money"
      subtitle="ERA (835) explains every paid, adjusted or denied line; EFT is the money itself. Both are matched and reconciled to the contract.">
      <Waterfall billed={billed} writeoff={Math.max(billed - allowed, 0)} allowed={allowed} insurer={insurer} patient={patient} />
      <div className="mt-4 space-y-3">
        {enc.remittance.map((r, i) => (
          <div key={i} className="rounded-xl border border-line bg-white/[0.02] p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm font-medium text-ink">{r.kind === "appeal" ? "Appeal ERA" : "ERA 835"} · {usd(r.total_paid, true)} by {r.method}</p>
              <Pill tone={r.reconciliation.status === "matched" ? "good" : "warning"}>Reconciled: {r.reconciliation.status}</Pill>
            </div>
            <p className="mt-0.5 text-xs text-ink-3">Paid {dateLabel(r.payment_date)} · EFT trace <span className="font-mono">{r.eft_trace}</span> · expected {usd(r.reconciliation.expected, true)}</p>
            <div className="mt-2 overflow-x-auto">
              <table className="w-full min-w-[600px] text-xs">
                <thead><tr className="text-left text-[11px] text-ink-3"><th className="py-1 pr-2">Line</th><th className="py-1 pr-2 text-right">Billed</th><th className="py-1 pr-2 text-right">Allowed</th><th className="py-1 pr-2 text-right">Paid</th><th className="py-1 pr-2 text-right">Patient</th><th className="py-1">Adjustments (CARC)</th></tr></thead>
                <tbody>
                  {r.lines.map((x) => (
                    <tr key={x.line_no} className="border-t border-line align-top">
                      <td className="py-1.5 pr-2 font-mono">{x.code}{x.modifier ? `-${x.modifier.split(" ").join("-")}` : ""}</td>
                      <td className="tabular py-1.5 pr-2 text-right">{usd(x.billed, true)}</td>
                      <td className="tabular py-1.5 pr-2 text-right">{usd(x.allowed, true)}</td>
                      <td className="tabular py-1.5 pr-2 text-right">{usd(x.paid, true)}</td>
                      <td className="tabular py-1.5 pr-2 text-right">{usd(x.patient_resp, true)}</td>
                      <td className="py-1.5 text-ink-3">{x.adjustments.map((a) => <span key={a.code} title={a.text} className="mr-2 whitespace-nowrap"><span className="font-mono text-ink-2">{a.code}</span> {usd(a.amount, true)}</span>)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-2"><Details summary="View the X12 835 (simplified)"><Pre>{r.x12_835}</Pre></Details></div>
          </div>
        ))}
      </div>
    </Section>
  );
}

// --------------------------------------------------------------------------- denial loop (slides 11-13)

export function AppealPanel({ enc, onDecide, busy }: { enc: EncounterDetail; onDecide: (a: "appeal" | "accept") => Promise<void>; busy: boolean }) {
  const ap = enc.appeal;
  const resolutions = Object.entries(ap?.resolutions ?? {});
  if (!ap || (!ap.letter && !resolutions.length)) return null;
  const pending = enc.attention === "denial" && ap.status === "drafted";
  return (
    <Section id="denial" step="Denial management" title="Identify, categorize, fix or appeal, prevent"
      subtitle="Only denials with something to gain are appealed; the rest are routed to the patient (ABN) or written off with a prevention note."
      right={ap.status ? <Pill tone={ap.status === "overturned" ? "good" : ap.status === "drafted" ? "warning" : "neutral"}>Appeal {ap.status}</Pill> : null}>
      {ap.letter && (
        <>
          {ap.assessment && (
            <p className="mb-3 text-xs text-ink-2"><span className="font-medium text-ink">{ap.code} denied {ap.carc}.</span> Success likelihood: <span className="font-medium">{ap.assessment.likelihood}</span>. {ap.assessment.reason}</p>
          )}
          <Pre>{ap.letter}</Pre>
          {pending && (
            <div className="mt-3 flex flex-wrap gap-2">
              <Btn variant="primary" busy={busy} onClick={() => onDecide("appeal")}><Send className="h-3.5 w-3.5" /> Approve and send appeal</Btn>
              <Btn busy={busy} onClick={() => onDecide("accept")}><Gavel className="h-3.5 w-3.5" /> Accept denial</Btn>
            </div>
          )}
        </>
      )}
      {resolutions.length > 0 && (
        <ul className="mt-3 space-y-1 text-xs text-ink-2">
          {resolutions.map(([k, r]) => <li key={k}><span className="font-mono">{r.code}</span> ({r.carc}): {titleCase(r.resolution)}</li>)}
        </ul>
      )}
    </Section>
  );
}

// --------------------------------------------------------------------------- steps 14-15

export function BillingPanel({ enc, onPay, busy }: { enc: EncounterDetail; onPay: (amount: number | null) => Promise<void>; busy: boolean }) {
  const st = enc.billing?.statement;
  const payments = enc.billing?.payments ?? [];
  const [amount, setAmount] = useState("");
  if (!st) return null; // the check-in copay alone is shown on the front-desk panel
  const due = Math.max(enc.balance, 0);
  return (
    <Section id="billing" step="Steps 14-15 · Patient billing and close" title="Patient statement"
      subtitle="What insurance did not cover, explained line by line. Paying online closes the account."
      right={enc.stage === "closed" ? <Pill tone="good">Account closed</Pill> : due > 0.004 ? <Pill tone="warning">{usd(due, true)} due</Pill> : null}>
      {st && (
        <>
          <ul className="divide-y divide-line rounded-xl border border-line">
            {st.items.map((it, i) => (
              <li key={i} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm">
                <div><span className="font-mono text-xs text-ink-3">{it.code}</span> <span className="text-ink-2">{it.description}</span>
                  <p className="text-[11px] text-ink-3">{it.why}</p></div>
                <span className="tabular font-medium text-ink">{usd(it.amount, true)}</span>
              </li>
            ))}
            {!st.items.length && <li className="px-3 py-3 text-sm text-ink-3">Nothing owed beyond what was paid at check-in.</li>}
          </ul>
          <div className="mt-3 grid gap-3 sm:grid-cols-2 2xl:grid-cols-4">
            <Stat label="Patient responsibility" value={usd(st.total_patient_responsibility, true)} />
            <Stat label="Paid to date" value={usd(enc.totals.patient_paid, true)} />
            <Stat label="Balance due" value={usd(due, true)} tone={due > 0.004 ? "warn" : "good"} hint={due > 0.004 ? `due ${dateLabel(st.due_date)}` : undefined} />
            <Stat label="AR aging" value={st.aging_bucket} hint="days since statement" />
          </div>
        </>
      )}
      {enc.attention === "patient_payment" && due > 0.004 && (
        <form className="mt-4 flex flex-wrap items-end gap-2" onSubmit={(e) => { e.preventDefault(); void onPay(amount ? Number(amount) : null); }}>
          <label className="text-xs text-ink-3">Amount (blank = full balance)
            <input value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ""))} inputMode="decimal" placeholder={due.toFixed(2)}
              className="mt-1 block w-32 rounded-lg border border-line bg-surface-2 px-2 py-1.5 text-sm text-ink" /></label>
          <Btn type="submit" variant="primary" busy={busy}><CreditCard className="h-3.5 w-3.5" /> Patient pays online</Btn>
          <span className="text-[11px] text-ink-3">Simulated card payment through the patient portal.</span>
        </form>
      )}
      {payments.length > 0 && (
        <div className="mt-4">
          <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-ink-3">Patient payments</h3>
          <ul className="space-y-1 text-xs text-ink-2">
            {payments.map((p, i) => <li key={i} className="flex justify-between gap-2"><span>{dateLabel(p.date)} · {p.note}</span><span className="tabular">{usd(p.amount, true)}</span></li>)}
          </ul>
        </div>
      )}
    </Section>
  );
}
