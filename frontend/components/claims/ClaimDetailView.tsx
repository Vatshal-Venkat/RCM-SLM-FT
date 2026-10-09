"use client";

import { ArrowLeft, Bot, Sparkles } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Collapsible, ExplainIcons, IssuesList, SourcesList, ValidationBadge } from "@/components/chat/Explain";
import { Card, CardHeader, ErrorState, PageHeader, Pill, SeverityTag, Skeleton, StatusBadge } from "@/components/ui/primitives";
import { useApi } from "@/hooks/useApi";
import { apiPost } from "@/lib/api";
import { dateLabel, titleCase, usd } from "@/lib/format";
import type { ClaimAnalysis, ClaimDetail } from "@/types/api";

export function ClaimDetailView({ claimId }: { claimId: string }) {
  const router = useRouter();
  const path = `/api/claims/${encodeURIComponent(claimId)}`;
  const { data: c, error, loading, reload } = useApi<ClaimDetail>(path);

  const back = (
    <button onClick={() => router.back()} className="inline-flex items-center gap-1.5 text-xs text-ink-3 hover:text-ink">
      <ArrowLeft className="h-3.5 w-3.5" /> Back
    </button>
  );

  if (error) return <div className="mx-auto max-w-[1400px] space-y-4">{back}<ErrorState message={error} onRetry={reload} /></div>;
  if (loading || !c) {
    return (
      <div className="mx-auto max-w-[1400px] space-y-4">
        {back}
        <Skeleton className="h-20 rounded-2xl" />
        <div className="grid gap-4 lg:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-48 rounded-2xl" />)}</div>
      </div>
    );
  }

  const ask = `What is going on with claim ${c.claim_id} and what should we do next?`;
  return (
    <div className="mx-auto max-w-[1400px]">
      <div className="mb-3">{back}</div>
      <PageHeader
        eyebrow="Claim"
        title={<span className="flex flex-wrap items-center gap-3">{c.claim_id} <StatusBadge status={c.status} /></span>}
        description={`${c.cpt_description} (CPT ${c.cpt_code}) · ${c.payer} · ${c.provider}`}
        right={
          <Link href={`/copilot?q=${encodeURIComponent(ask)}`}
            className="inline-flex items-center gap-1.5 rounded-xl border border-line bg-surface-2/70 px-3 py-2 text-sm text-ink-2 hover:border-accent/40 hover:text-ink">
            <Bot className="h-4 w-4 text-accent" /> Ask Copilot about this claim
          </Link>
        }
      />

      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader title="Amounts" />
          <Facts rows={[
            ["Billed", usd(c.billed_amount, true)], ["Allowed", usd(c.allowed_amount, true)], ["Payer paid", usd(c.paid_amount, true)],
            ["Patient responsibility", usd(c.patient_responsibility, true)], ["Patient paid", usd(c.patient_paid_amount, true)],
            ["Contractual adjustment", usd(c.contractual_adjustment, true)], ["Write-off", usd(c.writeoff_amount, true)],
            ["Balance", <b key="b" className="text-ink">{usd(c.balance, true)}</b>],
          ]} />
        </Card>
        <Card>
          <CardHeader title="Service & coding" />
          <Facts rows={[
            ["Service date", dateLabel(c.service_date)], ["Submitted", dateLabel(c.claim_date)],
            ["Adjudicated", dateLabel(c.adjudication_date)], ["Days in AR", String(c.days_in_ar)],
            ["Procedure", `CPT ${c.cpt_code}${c.modifier ? `-${c.modifier}` : ""} × ${c.units}`],
            ["Diagnosis", `${c.icd10_code} ${c.icd10_description}`], ["Place of service", c.place_of_service],
            ["Authorization", c.requires_authorization ? (c.authorization_number ?? "Required · none on file") : "Not required"],
          ]} />
        </Card>
        <Card>
          <CardHeader title="Payer & follow-up" />
          <Facts rows={[
            ["Payer", `${c.payer} (${titleCase(c.payer_type)})`], ["Provider", `${c.provider} · ${c.provider_specialty}`],
            ["Patient", `${c.patient.age_band} · ${c.patient.sex} · ${c.patient.state} (synthetic)`],
            ["Submissions", String(c.submission_count)],
            ["Timely filing", c.days_until_timely_filing >= 0 ? `${c.days_until_timely_filing} days left of ${c.timely_filing_days}` : `Passed ${-c.days_until_timely_filing} days ago`],
            ...(c.denial_reason_code ? [["Denial", `CARC ${c.denial_reason_code} · ${c.denial_reason}`] as [string, string]] : []),
            ...(c.rejection_reason ? [["Rejection", c.rejection_reason] as [string, string]] : []),
          ]} />
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-2">
        <ClaimAnalysisCard claimId={c.claim_id} />
        <Card>
          <CardHeader title="Status history" />
          <ol className="space-y-2 px-5 pb-4">
            {c.history.map((h, i) => (
              <li key={i} className="flex gap-3 text-xs">
                <span className="tabular w-24 shrink-0 text-ink-3">{dateLabel(h.status_date)}</span>
                <span className="text-ink-2"><StatusBadge status={h.status} />{h.note && <span className="ml-2">{h.note}</span>}</span>
              </li>
            ))}
          </ol>
          {c.denials.length > 0 && (
            <>
              <CardHeader title="Denials" />
              <Table head={["CARC", "Amount", "Date", "Appeal"]} rows={c.denials.map((d) => [
                `${d.group_code}-${d.carc_code} · ${d.description}`, usd(d.denied_amount, true), dateLabel(d.denial_date), titleCase(d.appeal_status),
              ])} />
            </>
          )}
          {c.payments.length > 0 && (
            <>
              <CardHeader title="Payments" />
              <Table head={["Source", "Amount", "Date", "Method"]} rows={c.payments.map((p) => [
                titleCase(p.source), usd(p.amount, true), dateLabel(p.payment_date), titleCase(p.method),
              ])} />
            </>
          )}
        </Card>
      </div>
    </div>
  );
}

function ClaimAnalysisCard({ claimId }: { claimId: string }) {
  const [a, setA] = useState<ClaimAnalysis | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async () => {
    setBusy(true);
    setError(null);
    try {
      setA(await apiPost<ClaimAnalysis>(`/api/claims/${encodeURIComponent(claimId)}/analyze`));
    } catch (e) {
      setError((e as Error).message || "Analysis failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader title="AI analysis" subtitle="Rule-based findings plus a validated SLM explanation"
        right={
          <button onClick={run} disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-lg bg-accent px-3 py-1.5 text-xs font-medium text-white hover:bg-accent/85 disabled:opacity-50">
            <Sparkles className="h-3.5 w-3.5" /> {busy ? "Analyzing…" : a ? "Re-run" : "Analyze with AI"}
          </button>
        } />
      <div className="space-y-3 px-5 pb-5">
        {error && <ErrorState message={error} onRetry={run} />}
        {!a && !error && !busy && <p className="text-xs text-ink-3">Runs on the local model and takes about 15-30 seconds.</p>}
        {busy && <Skeleton className="h-32" />}
        {a && !busy && (
          <>
            <div className="flex flex-wrap items-center gap-1.5">
              <ValidationBadge v={a.validation} />
              <Pill tone={a.confidence_label === "high" ? "good" : a.confidence_label === "medium" ? "warning" : "critical"}>
                Confidence {a.confidence_label}
              </Pill>
              {a.narrative_source === "rule_based_fallback" && <Pill tone="warning">Rule-based fallback</Pill>}
            </div>
            {a.issues.length > 0 && (
              <ul className="space-y-1.5">
                {a.issues.map((i, n) => (
                  <li key={n} className="text-xs text-ink-2"><SeverityTag severity={i.severity} /> <b className="ml-1 text-ink">{i.title}</b> · {i.detail}</li>
                ))}
              </ul>
            )}
            <div className="prose-rcm text-sm text-ink-2"><ReactMarkdown remarkPlugins={[remarkGfm]}>{a.narrative}</ReactMarkdown></div>
            {a.recommended_actions.length > 0 && (
              <div>
                <p className="text-xs font-medium text-ink">Recommended actions</p>
                <ol className="mt-1 list-decimal space-y-1 pl-5 text-xs text-ink-2">{a.recommended_actions.map((x, n) => <li key={n}>{x}</li>)}</ol>
              </div>
            )}
            {a.sources.length > 0 && (
              <Collapsible title={`Sources (${a.sources.length})`} icon={<ExplainIcons.BookOpen className="h-3.5 w-3.5" />}>
                <SourcesList sources={a.sources} />
              </Collapsible>
            )}
            <Collapsible title="Validation details"><IssuesList v={a.validation} /></Collapsible>
          </>
        )}
      </div>
    </Card>
  );
}

function Facts({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1.5 px-5 pb-4 text-xs">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-ink-3">{k}</dt>
          <dd className="tabular text-right text-ink-2">{v}</dd>
        </div>
      ))}
    </dl>
  );
}

function Table({ head, rows }: { head: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto px-3 pb-4">
      <table className="w-full text-xs">
        <thead><tr className="text-left text-ink-3">{head.map((h) => <th key={h} className="px-2 py-1.5 font-medium">{h}</th>)}</tr></thead>
        <tbody className="tabular">{rows.map((r, i) => (
          <tr key={i} className="border-t border-line">{r.map((x, j) => <td key={j} className="px-2 py-1.5 text-ink-2">{x}</td>)}</tr>
        ))}</tbody>
      </table>
    </div>
  );
}
