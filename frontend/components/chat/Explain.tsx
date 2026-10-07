"use client";

import clsx from "clsx";
import { BookOpen, ChevronDown, CircleCheck, Database, RefreshCcw, ShieldAlert, ShieldCheck } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Pill, SeverityTag } from "@/components/ui/primitives";
import { num, pct, titleCase, usd } from "@/lib/format";
import type { Source, Validation } from "@/types/api";

export function ValidationBadge({ v }: { v?: Validation }) {
  if (!v) return null;
  const errors = v.issues.filter((i) => i.severity === "error").length;
  const warnings = v.issues.filter((i) => i.severity === "warning").length;
  if (!v.passed) return <Pill tone="critical"><ShieldAlert className="h-3 w-3" /> Validation failed ({errors})</Pill>;
  return (
    <>
      <Pill tone="good" title="Checked for hallucinated definitions, KPI formulas, unsupported numbers, PHI, repetition and relevance">
        <ShieldCheck className="h-3 w-3" /> Validated{warnings ? ` · ${warnings} warning${warnings > 1 ? "s" : ""}` : ""}
      </Pill>
      {v.regenerated && <Pill tone="warning" title="The first draft failed validation and was regenerated with stronger grounding"><RefreshCcw className="h-3 w-3" /> Regenerated</Pill>}
    </>
  );
}

export function SourcesList({ sources }: { sources: Source[] }) {
  if (!sources.length) return null;
  return (
    <ol className="space-y-2">
      {sources.map((s) => (
        <li key={`${s.ref}-${s.document}-${s.section}`} className="rounded-xl border border-line bg-surface-2/60 p-3">
          <div className="flex items-start justify-between gap-3">
            <p className="text-xs font-medium text-ink">
              <span className="mr-1.5 rounded bg-accent/15 px-1.5 py-0.5 text-[10px] text-[#b9c2ff]">{s.ref}</span>
              {s.section ?? s.title}
            </p>
            <span className="tabular shrink-0 text-[10px] text-ink-3" title="Cross-encoder relevance">{(s.score * 100).toFixed(0)}%</span>
          </div>
          <p className="mt-1 text-[11px] text-ink-3">{s.document}</p>
          <p className="mt-1.5 line-clamp-3 text-xs leading-relaxed text-ink-2">{s.snippet}</p>
        </li>
      ))}
    </ol>
  );
}

export function IssuesList({ v }: { v?: Validation }) {
  if (!v?.issues.length) return <p className="flex items-center gap-1.5 text-xs text-ink-3"><CircleCheck className="h-3.5 w-3.5" /> No issues found.</p>;
  return (
    <ul className="space-y-1.5">
      {v.issues.map((i, n) => (
        <li key={n} className="text-xs text-ink-2"><SeverityTag severity={i.severity} /> <span className="ml-1">{i.message}</span></li>
      ))}
    </ul>
  );
}

export function Collapsible({ title, icon, children, defaultOpen = false }: {
  title: string; icon?: React.ReactNode; children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="rounded-xl border border-line">
      <button onClick={() => setOpen(!open)} aria-expanded={open}
        className="flex w-full items-center justify-between px-3 py-2 text-xs font-medium text-ink-2 hover:text-ink">
        <span className="flex items-center gap-1.5">{icon}{title}</span>
        <ChevronDown className={clsx("h-4 w-4 transition-transform", open && "rotate-180")} />
      </button>
      {open && <div className="border-t border-line p-3">{children}</div>}
    </div>
  );
}

type Row = Record<string, unknown>;

/** Renders the deterministic analytics behind a Copilot answer. */
export function DataView({ data }: { data: Record<string, unknown> }) {
  const type = data.type as string;
  const table = (head: string[], rows: (string | React.ReactNode)[][]) => (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead><tr className="text-left text-ink-3">{head.map((h) => <th key={h} className="px-2 py-1.5 font-medium">{h}</th>)}</tr></thead>
        <tbody className="tabular">{rows.map((r, i) => (
          <tr key={i} className="border-t border-line">{r.map((c, j) => <td key={j} className={clsx("px-2 py-1.5", j ? "text-right text-ink-2" : "text-ink")}>{c}</td>)}</tr>
        ))}</tbody>
      </table>
    </div>
  );

  if (type === "ranking") {
    const rows = (data.rows as Row[]) ?? [];
    const metric = data.metric as string;
    const fmt = (v: unknown) => metric === "outstanding_ar" ? usd(v as number) : metric === "avg_days_to_adjudicate" ? `${(v as number)?.toFixed(1)} d` : pct(v as number);
    return table(["Rank", titleCase(data.dimension as string), titleCase(metric), "Denied / adjudicated"],
      rows.map((r, i) => [`#${i + 1}`, r.name as string, fmt(r[metric]), `${num(r.denied as number)} / ${num(r.adjudicated as number)}`]));
  }
  if (type === "denial_drivers") {
    const payers = (data.by_payer as Row[]).slice(0, 4);
    const reasons = (data.by_reason as Row[]).slice(0, 4);
    return (
      <div className="space-y-3">
        <p className="text-xs text-ink-2">
          Denial rate <b className="text-ink">{pct(data.denial_rate_before as number)}</b> → <b className="text-ink">{pct(data.denial_rate_now as number)}</b>
          {" "}({(data.change_pts as number) > 0 ? "+" : ""}{(data.change_pts as number).toFixed(1)} pts). Contributions sum to the change.
        </p>
        {table(["Payer", "Before", "Now", "Contribution"], payers.map((r) => [r.payer as string, pct(r.denial_rate_before as number), pct(r.denial_rate_now as number), `${(r.contribution_pts as number) > 0 ? "+" : ""}${(r.contribution_pts as number).toFixed(2)} pts`]))}
        {table(["CARC", "Before", "Now", "Contribution"], reasons.map((r) => [`${r.carc} · ${r.description}`, num(r.denials_before as number), num(r.denials_now as number), `${(r.contribution_pts as number) > 0 ? "+" : ""}${(r.contribution_pts as number).toFixed(2)} pts`]))}
      </div>
    );
  }
  if (type === "ar_drivers") {
    return (
      <div className="space-y-3">
        <p className="text-xs text-ink-2">AR <b className="text-ink">{usd(data.ar_before as number)}</b> → <b className="text-ink">{usd(data.ar_now as number)}</b> · Days in AR {String(data.days_in_ar_before)} → {String(data.days_in_ar_now)}</p>
        {table(["Payer", "AR before", "AR now", "Change"], (data.by_payer as Row[]).slice(0, 6).map((r) => [r.payer as string, usd(r.ar_before as number), usd(r.ar_now as number), usd(r.change as number)]))}
        {table(["Payer", "Days to adjudicate before", "Now", "Pending"], (data.payer_speed as Row[]).slice(0, 6).map((r) => [r.payer as string, String(r.avg_days_to_adjudicate_before ?? "—"), String(r.avg_days_to_adjudicate_now ?? "—"), num(r.pending_claims_now as number)]))}
      </div>
    );
  }
  if (type === "prioritization") {
    return table(["Claim", "Payer", "Status", "Balance", "Score"], (data.top_claims as Row[]).map((r) => [
      <Link key={r.claim_id as string} href={`/claims/${r.claim_id}`} className="text-accent hover:underline">{r.claim_id as string}</Link>,
      r.payer as string, titleCase(r.status as string), usd(r.balance as number), (r.score as number).toFixed(1)]));
  }
  if (type === "denial_causes") {
    return table(["Category", "Denials", "Share", "Denied $"], (data.categories as Row[]).map((r) => [titleCase(r.category as string), num(r.count as number), pct(r.share_pct as number), usd(r.denied_amount as number)]));
  }
  if (type === "kpi_summary") {
    const c = data.current as Row, p = data.previous as Row;
    const keys: [string, string, (v: number) => string][] = [["denial_rate", "Denial rate", pct], ["clean_claim_rate", "Clean claim rate", pct],
      ["first_pass_resolution_rate", "First pass resolution", pct], ["days_in_ar", "Days in AR", (v) => v?.toFixed(1)], ["outstanding_ar", "Outstanding AR", usd]];
    return table(["KPI", "Previous", "Current"], keys.map(([k, l, f]) => [l, f(p[k] as number), f(c[k] as number)]));
  }
  if (type === "claim" && data.found) {
    return <Link href={`/claims/${data.claim_id}`} className="text-xs text-accent hover:underline">Open claim {String(data.claim_id)} →</Link>;
  }
  return null;
}

export const ExplainIcons = { BookOpen, Database };
