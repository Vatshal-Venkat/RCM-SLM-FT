"use client";

import { Cpu, Database, GitBranch, RefreshCcw, Search, ShieldCheck } from "lucide-react";

import { Card, CardHeader, ErrorState, PageHeader, Pill, Skeleton } from "@/components/ui/primitives";
import { useApi } from "@/hooks/useApi";
import { titleCase } from "@/lib/format";
import type { Health, KnowledgeIndex, ModelInfo } from "@/types/api";

const PIPELINE = [
  { icon: GitBranch, title: "Intent routing", text: "A rule-based router (no model call) sends each question to knowledge, analytics, claim or data-query handling, and answers greetings and off-topic questions without the model." },
  { icon: Search, title: "Grounding", text: "Knowledge questions retrieve passages with hybrid search (BGE embeddings + BM25, fused, then cross-encoder reranked). Validated definitions are pinned for critical terms. Data questions get an exact fact sheet computed in SQL." },
  { icon: Cpu, title: "Generation", text: "The fine-tuned Qwen3 1.7B model runs locally through llama.cpp on the CPU, answering only from the supplied references and data." },
  { icon: ShieldCheck, title: "Validation", text: "Every answer is checked for acronym expansions, misdefinitions, KPI formulas, numbers not in the data, invented claim/payer/provider IDs, PHI, repetition and relevance." },
  { icon: RefreshCcw, title: "Repair", text: "A failed answer is regenerated once with stronger grounding. If definitions are still contradicted, the validated definition is shown instead, and unverified IDs are masked." },
];

export default function ModelPage() {
  const model = useApi<ModelInfo>("/api/model");
  const health = useApi<Health>("/health");
  const idx = useApi<KnowledgeIndex>("/api/rag/documents");
  const m = model.data;

  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader eyebrow="Model" title="AI model & pipeline"
        description="The local small language model behind the Copilot, and the grounding and validation steps every answer goes through." />
      {(model.error || health.error) && <ErrorState message={model.error || health.error || ""} onRetry={() => { model.reload(); health.reload(); }} />}

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title={m?.name ?? "Language model"} subtitle={m?.provider}
            right={m && <Pill tone={m.loaded ? "good" : "critical"}>{m.loaded ? "Loaded" : "Not loaded"}</Pill>} />
          {!m ? <Skeleton className="m-4 h-48" /> : (
            <dl className="grid grid-cols-1 gap-x-8 gap-y-2 px-5 pb-5 text-sm sm:grid-cols-2">
              {Object.entries(m.details).map(([k, v]) => (
                <div key={k} className="flex justify-between gap-4 border-b border-line py-1.5">
                  <dt className="text-ink-3">{titleCase(k)}</dt>
                  <dd className="tabular text-right text-ink">{v === null ? "—" : typeof v === "boolean" ? (v ? "Yes" : "No") : String(v)}</dd>
                </div>
              ))}
            </dl>
          )}
        </Card>

        <Card>
          <CardHeader title="Components" subtitle="Live status from the backend" />
          {!health.data ? <Skeleton className="m-4 h-32" /> : (
            <ul className="space-y-3 px-5 pb-5 text-sm">
              <li className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-ink-2"><Cpu className="h-4 w-4" /> Language model</span>
                <Pill tone={health.data.components.llm.ready ? "good" : "critical"}>{health.data.components.llm.ready ? "Ready" : "Unavailable"}</Pill>
              </li>
              <li className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-ink-2"><Search className="h-4 w-4" /> Knowledge index</span>
                <Pill tone={health.data.components.rag.ready ? "good" : "critical"}>{health.data.components.rag.ready ? "Ready" : "Not built"}</Pill>
              </li>
              <li className="flex items-center justify-between">
                <span className="flex items-center gap-2 text-ink-2"><Database className="h-4 w-4" /> Overall</span>
                <Pill tone={health.data.status === "ok" ? "good" : "warning"}>{titleCase(health.data.status)}</Pill>
              </li>
              {idx.data?.ready && (
                <li className="border-t border-line pt-3 text-xs text-ink-3">
                  Embeddings: {idx.data.embedding_model}<br />Reranker: {idx.data.reranker_model ?? "off"}<br />
                  {idx.data.n_chunks} chunks from {idx.data.n_documents} documents
                </li>
              )}
            </ul>
          )}
        </Card>
      </div>

      <Card className="mt-4">
        <CardHeader title="How an answer is produced" />
        <ol className="grid gap-3 px-5 pb-5 md:grid-cols-5">
          {PIPELINE.map((s, n) => (
            <li key={s.title} className="rounded-xl border border-line bg-surface-2/60 p-3">
              <p className="flex items-center gap-2 text-sm font-medium text-ink">
                <span className="grid h-6 w-6 place-items-center rounded-full bg-accent/15 text-[11px] text-[#b9c2ff]">{n + 1}</span>
                <s.icon className="h-4 w-4 text-accent" /> {s.title}
              </p>
              <p className="mt-2 text-xs leading-relaxed text-ink-2">{s.text}</p>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
