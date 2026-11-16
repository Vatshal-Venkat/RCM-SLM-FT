"use client";

import clsx from "clsx";
import { ChevronDown, ChevronUp, PenLine, Plus, Search, ShieldCheck, Star, X } from "lucide-react";
import { Fragment, useEffect, useState } from "react";

import { Btn, CoverageBadge, DECISIONS, Section, Stat } from "@/components/journey/shared";
import { Pill } from "@/components/ui/primitives";
import { apiGet, toQuery } from "@/lib/api";
import { titleCase, usd } from "@/lib/format";
import type { BillingDecision, CodeSearch, EncounterDetail, ServiceLine, SoapNote } from "@/types/journey";

// --------------------------------------------------------------------------- SOAP note

export function NotePanel({ note, signed, doctor }: { note: SoapNote; signed: boolean; doctor: string }) {
  const vitals = Object.entries(note.objective.vitals);
  return (
    <Section id="note" step="Step 7 · Clinical documentation" title="SOAP note"
      subtitle={signed ? `Signed by ${doctor}` : "Drafted by the AI scribe from the conversation. Review and sign below."}
      right={signed ? <Pill tone="good">Signed</Pill> : <Pill tone="warning">Draft, needs signature</Pill>}>
      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-3">
          <Block label="Chief complaint"><p className="text-sm text-ink">{note.chief_complaint}</p></Block>
          <Block label="S · History of present illness">
            <ul className="list-disc space-y-1 pl-4 text-sm text-ink-2">{note.subjective.hpi.map((h, i) => <li key={i}>{h}</li>)}</ul>
            {note.subjective.pertinent_negatives.length > 0 && (
              <p className="mt-2 text-xs text-ink-3">Denies: {note.subjective.pertinent_negatives.join("; ")}</p>
            )}
          </Block>
          <Block label="O · Objective">
            {vitals.length > 0 && (
              <div className="mb-2 flex flex-wrap gap-1.5">
                {vitals.map(([k, v]) => <Pill key={k}>{titleCase(k)}: {v}</Pill>)}
              </div>
            )}
            <ul className="list-disc space-y-1 pl-4 text-sm text-ink-2">{note.objective.exam.map((h, i) => <li key={i}>{h}</li>)}</ul>
            {!vitals.length && !note.objective.exam.length && <p className="text-xs text-ink-3">No exam findings spoken aloud.</p>}
          </Block>
        </div>
        <div className="space-y-3">
          <Block label="A · Assessment">
            <ul className="space-y-1 text-sm">
              {note.assessment.map((a) => (
                <li key={a.code} className="flex gap-2"><span className="font-mono text-xs text-accent-2">{a.code}</span><span className="text-ink-2">{a.description}</span></li>
              ))}
            </ul>
          </Block>
          <Block label="P · Plan">
            <ul className="list-disc space-y-1 pl-4 text-sm text-ink-2">
              {note.plan.orders.map((o) => <li key={o}>Order: {o}</li>)}
              {note.plan.prescriptions.map((o) => <li key={o}>Rx: {o}</li>)}
              {note.plan.otc.map((o) => <li key={o}>OTC: {o}</li>)}
              {note.plan.follow_up && <li>Follow-up: {note.plan.follow_up}</li>}
            </ul>
          </Block>
          {note.not_coded.length > 0 && (
            <Block label="Held back by the AI (not coded)">
              <ul className="space-y-1.5 text-xs">
                {note.not_coded.map((n, i) => (
                  <li key={i}><span className="font-medium text-ink-2">{n.finding}</span> · <span className="text-ink-3">{n.reason}</span>
                    <p className="italic text-ink-3">{n.quote}</p></li>
                ))}
              </ul>
            </Block>
          )}
          {note.evidence.length > 0 && (
            <Block label="Medical-necessity evidence found">
              <ul className="space-y-1.5 text-xs">
                {note.evidence.map((e) => <li key={e.tag}><span className="text-good">{e.label}</span><p className="italic text-ink-3">&ldquo;{e.quote}&rdquo;</p></li>)}
              </ul>
            </Block>
          )}
        </div>
      </div>
    </Section>
  );
}

function Block({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-line bg-white/[0.02] p-3">
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wider text-ink-3">{label}</p>
      {children}
    </div>
  );
}

// --------------------------------------------------------------------------- coding + coverage

interface DraftLine { code: string; description: string; modifier: string; units: number; billing_decision: BillingDecision | "" }

export function CodingPanel({ enc, onSave, onSign, busy }: {
  enc: EncounterDetail;
  onSave: (diagnoses: string[], lines: { code: string; modifier: string | null; units: number; billing_decision: BillingDecision | null }[]) => Promise<boolean>;
  onSign: () => Promise<void>;
  busy: boolean;
}) {
  const coding = enc.coding!;
  const editable = enc.stage === "coded" && !enc.signed;
  const [open, setOpen] = useState<number | null>(null);
  const [editing, setEditing] = useState(false);
  const [dx, setDx] = useState<{ code: string; description: string }[]>([]);
  const [lines, setLines] = useState<DraftLine[]>([]);

  const startEdit = () => {
    setDx(coding.diagnoses.map((d) => ({ code: d.code, description: d.description })));
    setLines(enc.lines.map((l) => ({ code: l.code, description: l.description, modifier: l.modifier ?? "", units: l.units, billing_decision: l.billing_decision })));
    setEditing(true);
  };
  const save = async () => {
    const ok = await onSave(dx.map((d) => d.code), lines.map((l) => ({
      code: l.code, modifier: l.modifier.trim().toUpperCase() || null, units: l.units, billing_decision: l.billing_decision || null,
    })));
    if (ok) setEditing(false);
  };

  const live = enc.lines.filter((l) => l.billing_decision !== "do_not_perform");
  const estPayer = live.reduce((s, l) => s + l.est_payer, 0);
  const estPatient = live.reduce((s, l) => s + l.est_patient, 0);
  const flagged = enc.lines.filter((l) => l.coverage_status === "not_covered" || l.coverage_status === "medical_necessity_risk" || l.auth_status === "denied");

  return (
    <Section id="coding" step="Steps 8-9 · Charge capture, medical coding and coverage" title="Codes and insurance coverage"
      subtitle="ICD-10-CM explains why, CPT/HCPCS explains what. Every service is checked against the patient's plan before the claim exists."
      right={editable && !editing ? (
        <div className="flex gap-2">
          <Btn onClick={startEdit}><PenLine className="h-3.5 w-3.5" /> Edit codes</Btn>
          <Btn variant="primary" busy={busy} onClick={onSign}><ShieldCheck className="h-3.5 w-3.5" /> Sign note &amp; codes</Btn>
        </div>
      ) : enc.signed ? <Pill tone="good">Signed</Pill> : null}>

      {editing ? (
        <CodingEditor dx={dx} setDx={setDx} lines={lines} setLines={setLines} busy={busy} onSave={save} onCancel={() => setEditing(false)} />
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            <Stat label="Estimated insurance pays" value={usd(estPayer, true)} />
            <Stat label="Estimated patient pays" value={usd(estPatient, true)} hint="copay, deductible, coinsurance and self-pay" />
            <Stat label="Coverage flags" value={flagged.length ? `${flagged.length} service${flagged.length > 1 ? "s" : ""}` : "None"}
              tone={flagged.length ? "warn" : "good"} hint={flagged.length ? "caught before the claim goes out" : "everything is covered"} />
          </div>

          <h3 className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wider text-ink-3">Diagnoses (ICD-10-CM)</h3>
          <ul className="space-y-2">
            {coding.diagnoses.map((d) => (
              <li key={d.code} className="rounded-xl border border-line bg-white/[0.02] px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-sm font-semibold text-accent-2">{d.code}</span>
                  <span className="text-sm text-ink">{d.description}</span>
                  {d.primary && <Pill tone="accent">Primary</Pill>}
                  <span className={clsx("ml-auto text-[11px]", d.confidence < 0.8 ? "text-warning" : "text-ink-3")}>{Math.round(d.confidence * 100)}% confidence</span>
                </div>
                {d.evidence && <p className="mt-1 text-xs italic text-ink-3">{d.evidence}</p>}
                {d.rationale && <p className="mt-0.5 text-[11px] text-ink-3">{d.rationale}</p>}
              </li>
            ))}
            {coding.diagnoses.length === 0 && <li className="text-sm text-warning">No diagnosis found. Edit codes to add one before signing.</li>}
          </ul>
          {coding.warnings.length > 0 && (
            <ul className="mt-2 space-y-0.5 text-[11px] text-ink-3">{coding.warnings.map((w) => <li key={w}>Coding rule: {w}</li>)}</ul>
          )}

          <div className="mt-5 grid gap-2 rounded-xl border border-line bg-white/[0.02] p-3 sm:grid-cols-4">
            <div><p className="text-[11px] text-ink-3">E/M level (2021 MDM)</p>
              <p className="text-sm font-semibold text-ink">{[coding.em.preventive_code, coding.em.code].filter(Boolean).join(" + ")} · {titleCase(coding.em.mdm)}</p></div>
            {(["problems", "data", "risk"] as const).map((k) => (
              <div key={k}><p className="text-[11px] text-ink-3">{titleCase(k)}: <span className="text-ink-2">{coding.em[k].level}</span></p>
                <p className="text-[11px] leading-snug text-ink-3">{coding.em[k].why}</p></div>
            ))}
          </div>

          <h3 className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wider text-ink-3">Services (CPT / HCPCS) and coverage</h3>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-sm">
              <thead>
                <tr className="text-left text-[11px] text-ink-3">
                  <th className="px-2 py-1.5 font-medium">Code</th><th className="px-2 py-1.5 font-medium">Service</th>
                  <th className="px-2 py-1.5 font-medium">Dx</th><th className="px-2 py-1.5 text-right font-medium">Charge</th>
                  <th className="px-2 py-1.5 font-medium">Coverage</th><th className="px-2 py-1.5 font-medium">Decision</th>
                  <th className="px-2 py-1.5 text-right font-medium">Insurance</th><th className="px-2 py-1.5 text-right font-medium">Patient</th><th />
                </tr>
              </thead>
              <tbody>
                {enc.lines.map((l) => (
                  <Fragment key={l.line_no}>
                    <tr className={clsx("cursor-pointer border-t border-line hover:bg-white/[0.02]", l.billing_decision === "do_not_perform" && "opacity-60")}
                      onClick={() => setOpen(open === l.line_no ? null : l.line_no)}>
                      <td className="whitespace-nowrap px-2 py-2 font-mono text-xs">
                        <span className="font-semibold text-ink">{l.code}</span>
                        {l.modifier && <span className="ml-1 text-accent-2">-{l.modifier.split(" ").join("-")}</span>}
                      </td>
                      <td className="px-2 py-2 text-xs text-ink-2">{l.description}
                        {l.confidence < 0.8 && <span className="ml-1 text-warning">· review</span>}</td>
                      <td className="px-2 py-2 font-mono text-[11px] text-ink-3">{l.dx_codes.join(", ")}</td>
                      <td className="tabular px-2 py-2 text-right text-xs">{usd(l.charge * l.units, true)}</td>
                      <td className="px-2 py-2"><CoverageBadge status={l.coverage_status} auth={l.auth_status} /></td>
                      <td className="whitespace-nowrap px-2 py-2 text-xs text-ink-2">{DECISIONS[l.billing_decision]}</td>
                      <td className="tabular px-2 py-2 text-right text-xs">{usd(l.est_payer, true)}</td>
                      <td className="tabular px-2 py-2 text-right text-xs">{usd(l.est_patient, true)}</td>
                      <td className="px-1 text-ink-3">{open === l.line_no ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}</td>
                    </tr>
                    {open === l.line_no && <tr><td colSpan={9} className="px-2 pb-3"><LineDetail l={l} /></td></tr>}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </Section>
  );
}

function LineDetail({ l }: { l: ServiceLine }) {
  const cs = l.cost_share;
  return (
    <div className="grid gap-3 rounded-xl bg-white/[0.03] p-3 text-xs md:grid-cols-2">
      <div className="space-y-1.5">
        {l.rationale && <p><span className="text-ink-3">Coder rationale: </span><span className="text-ink-2">{l.rationale}</span></p>}
        {l.evidence && <p><span className="text-ink-3">From the conversation: </span><span className="italic text-ink-2">{l.evidence}</span></p>}
        <p className="text-ink-3">Source: {l.source === "ai" ? "AI coder" : l.source === "rule" ? "coding rule" : "physician"} · {Math.round(l.confidence * 100)}% confidence</p>
      </div>
      <div className="space-y-1.5">
        {l.coverage_reason && <p><span className="text-ink-3">Coverage: </span><span className="text-ink-2">{l.coverage_reason}</span></p>}
        {l.auth_number && <p className="text-ink-3">Authorization number <span className="font-mono text-ink">{l.auth_number}</span></p>}
        {cs && (
          <p className="text-ink-3">Patient share: {[
            cs.copay ? `copay ${usd(cs.copay, true)}` : null, cs.deductible ? `deductible ${usd(cs.deductible, true)}` : null,
            cs.coinsurance ? `coinsurance ${usd(cs.coinsurance, true)}` : null, cs.self_pay ? `self-pay price ${usd(cs.self_pay, true)}` : null,
            cs.abn_liability ? `if denied (ABN) ${usd(cs.abn_liability, true)}` : null,
          ].filter(Boolean).join(", ") || "none"}</p>
        )}
        {l.claim_id && <p className="text-ink-3">Claim line <a className="font-mono text-accent hover:underline" href={`/claims/${l.claim_id}`}>{l.claim_id}</a></p>}
      </div>
    </div>
  );
}

function CodingEditor({ dx, setDx, lines, setLines, busy, onSave, onCancel }: {
  dx: { code: string; description: string }[]; setDx: (d: { code: string; description: string }[]) => void;
  lines: DraftLine[]; setLines: (l: DraftLine[]) => void; busy: boolean; onSave: () => void; onCancel: () => void;
}) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<CodeSearch | null>(null);
  useEffect(() => {
    const ctrl = new AbortController();
    const t = setTimeout(() => {
      apiGet<CodeSearch>(`/api/encounters/codes${toQuery({ q: q.replace(/[^A-Za-z0-9 .\-]/g, "") })}`, ctrl.signal).then(setResults).catch(() => {});
    }, 200);
    return () => { clearTimeout(t); ctrl.abort(); };
  }, [q]);
  const update = (i: number, patch: Partial<DraftLine>) => setLines(lines.map((l, j) => (j === i ? { ...l, ...patch } : l)));

  return (
    <div className="space-y-4">
      <div>
        <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-3">Diagnoses (first = primary)</h3>
        <div className="flex flex-wrap gap-2">
          {dx.map((d, i) => (
            <span key={d.code} className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-white/[0.03] px-2 py-1 text-xs">
              {i === 0 ? <Star className="h-3 w-3 text-warning" aria-label="Primary" /> : (
                <button aria-label={`Make ${d.code} primary`} onClick={() => setDx([d, ...dx.filter((x) => x.code !== d.code)])} className="text-ink-3 hover:text-warning"><Star className="h-3 w-3" /></button>
              )}
              <span className="font-mono text-accent-2">{d.code}</span><span className="max-w-[220px] truncate text-ink-2">{d.description}</span>
              <button aria-label={`Remove ${d.code}`} onClick={() => setDx(dx.filter((x) => x.code !== d.code))} className="text-ink-3 hover:text-critical"><X className="h-3 w-3" /></button>
            </span>
          ))}
        </div>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full min-w-[640px] text-xs">
          <thead><tr className="text-left text-[11px] text-ink-3"><th className="px-2 py-1">Code</th><th className="px-2 py-1">Service</th><th className="px-2 py-1">Modifiers</th><th className="px-2 py-1">Units</th><th className="px-2 py-1">Decision</th><th /></tr></thead>
          <tbody>
            {lines.map((l, i) => (
              <tr key={`${l.code}-${i}`} className="border-t border-line">
                <td className="px-2 py-1.5 font-mono font-semibold">{l.code}</td>
                <td className="px-2 py-1.5 text-ink-2">{l.description}</td>
                <td className="px-2 py-1.5"><input aria-label={`Modifiers for ${l.code}`} value={l.modifier} maxLength={11}
                  onChange={(e) => update(i, { modifier: e.target.value.toUpperCase().replace(/[^0-9A-Z ]/g, "") })}
                  className="w-24 rounded border border-line bg-surface-2 px-1.5 py-0.5 font-mono" placeholder="25 RT" /></td>
                <td className="px-2 py-1.5"><input aria-label={`Units for ${l.code}`} type="number" min={1} max={99} value={l.units}
                  onChange={(e) => update(i, { units: Math.max(1, Math.min(99, Number(e.target.value) || 1)) })}
                  className="w-14 rounded border border-line bg-surface-2 px-1.5 py-0.5" /></td>
                <td className="px-2 py-1.5"><select aria-label={`Billing decision for ${l.code}`} value={l.billing_decision}
                  onChange={(e) => update(i, { billing_decision: e.target.value as BillingDecision | "" })}
                  className="rounded border border-line bg-surface-2 px-1.5 py-0.5">
                  <option value="">Automatic</option>
                  {Object.entries(DECISIONS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                </select></td>
                <td className="px-2 py-1.5"><button aria-label={`Remove ${l.code}`} onClick={() => setLines(lines.filter((_, j) => j !== i))} className="text-ink-3 hover:text-critical"><X className="h-3.5 w-3.5" /></button></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="rounded-xl border border-line bg-white/[0.02] p-3">
        <label className="flex items-center gap-2 text-xs text-ink-3"><Search className="h-3.5 w-3.5" />
          <input value={q} onChange={(e) => setQ(e.target.value)} maxLength={40} placeholder="Search codes to add (e.g. 99214, knee, vitamin)"
            className="min-w-0 flex-1 bg-transparent text-sm text-ink placeholder:text-ink-3 focus:outline-none" /></label>
        {results && (
          <div className="mt-2 grid max-h-56 gap-3 overflow-y-auto md:grid-cols-2">
            <ul className="space-y-1">{results.diagnoses.slice(0, 12).map((d) => (
              <li key={d.code}><button disabled={dx.some((x) => x.code === d.code)} onClick={() => setDx([...dx, d])}
                className="flex w-full items-center gap-2 rounded px-1.5 py-1 text-left text-xs hover:bg-white/5 disabled:opacity-40">
                <Plus className="h-3 w-3 shrink-0 text-ink-3" /><span className="font-mono text-accent-2">{d.code}</span><span className="truncate text-ink-2">{d.description}</span></button></li>))}
            </ul>
            <ul className="space-y-1">{results.services.slice(0, 12).map((s) => (
              <li key={s.code}><button onClick={() => setLines([...lines, { code: s.code, description: s.description, modifier: "", units: 1, billing_decision: "" }])}
                className="flex w-full items-center gap-2 rounded px-1.5 py-1 text-left text-xs hover:bg-white/5">
                <Plus className="h-3 w-3 shrink-0 text-ink-3" /><span className="font-mono text-ink">{s.code}</span><span className="truncate text-ink-2">{s.description}</span>
                <span className="ml-auto tabular text-ink-3">{usd(s.charge)}</span></button></li>))}
            </ul>
          </div>
        )}
      </div>
      <div className="flex justify-end gap-2">
        <Btn variant="ghost" onClick={onCancel}>Cancel</Btn>
        <Btn variant="primary" busy={busy} disabled={!dx.length || !lines.length} onClick={onSave}>Save and re-check coverage</Btn>
      </div>
    </div>
  );
}
