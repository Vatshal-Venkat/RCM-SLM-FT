"use client";

import { BookOpenText, Search } from "lucide-react";
import { useState } from "react";

import { Card, CardHeader, EmptyState, ErrorState, PageHeader, Pill, Skeleton } from "@/components/ui/primitives";
import { useApi } from "@/hooks/useApi";
import { apiPost } from "@/lib/api";
import { num, titleCase } from "@/lib/format";
import type { KnowledgeIndex, RagSearchResponse } from "@/types/api";

const EXAMPLES = ["What is an ERA?", "CARC 197 authorization denial", "How is Days in AR calculated?", "timely filing appeal"];

export default function KnowledgePage() {
  const idx = useApi<KnowledgeIndex>("/api/rag/documents");
  const [query, setQuery] = useState("");
  const [res, setRes] = useState<RagSearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const run = async (q: string) => {
    const text = q.trim();
    if (text.length < 2) return;
    setQuery(text);
    setBusy(true);
    setError(null);
    try {
      setRes(await apiPost<RagSearchResponse>("/api/rag/search", { query: text, k: 8 }));
    } catch (e) {
      setError((e as Error).message || "Search failed");
    } finally {
      setBusy(false);
    }
  };

  const i = idx.data;
  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader eyebrow="RCM Knowledge" title="Knowledge base"
        description="The validated documents the Copilot retrieves from. Search exactly as the Copilot does: dense embeddings + BM25, fused and reranked by a cross-encoder." />

      {idx.error && <ErrorState message={idx.error} onRetry={idx.reload} />}

      <div className="mb-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        {[
          ["Index", i ? (i.ready ? "Ready" : "Not built") : null],
          ["Documents", i ? num(i.n_documents) : null],
          ["Chunks", i ? num(i.n_chunks) : null],
          ["Built", i?.built_at ? new Date(i.built_at).toLocaleString() : i ? "—" : null],
        ].map(([label, value]) => (
          <Card key={label} className="p-4">
            <p className="text-xs text-ink-3">{label}</p>
            {value !== null ? <p className="mt-1 truncate text-lg font-semibold text-ink">{value}</p> : <Skeleton className="mt-2 h-6 w-20" />}
          </Card>
        ))}
      </div>

      <Card className="mb-4">
        <CardHeader title="Search the knowledge base" subtitle={i?.embedding_model ? `${i.embedding_model} · reranker ${i.reranker_model ?? "off"}` : undefined} />
        <div className="px-5 pb-5">
          <form className="flex gap-2" onSubmit={(e) => { e.preventDefault(); void run(query); }}>
            <label className="relative flex-1">
              <Search className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-ink-3" aria-hidden />
              <input value={query} onChange={(e) => setQuery(e.target.value.slice(0, 500))} placeholder="e.g. difference between a rejection and a denial"
                aria-label="Search query"
                className="h-9 w-full rounded-lg border border-line bg-surface-2 pl-9 pr-3 text-sm text-ink outline-none focus:border-accent/60 focus:ring-2 focus:ring-accent/20" />
            </label>
            <button type="submit" disabled={busy || query.trim().length < 2}
              className="rounded-lg bg-accent px-4 text-sm font-medium text-white hover:bg-accent/85 disabled:opacity-40">
              {busy ? "Searching…" : "Search"}
            </button>
          </form>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {EXAMPLES.map((q) => (
              <button key={q} onClick={() => void run(q)} className="rounded-full border border-line px-2.5 py-0.5 text-[11px] text-ink-2 hover:border-accent/40 hover:text-ink">{q}</button>
            ))}
          </div>

          {error && <div className="mt-4"><ErrorState message={error} onRetry={() => void run(query)} /></div>}
          {res && !busy && (
            <div className="mt-4">
              <p className="mb-2 text-xs text-ink-3">{res.results.length} results for “{res.query}” in {res.took_ms.toFixed(0)} ms</p>
              {res.results.length === 0 ? <EmptyState message="No matching passages." /> : (
                <ol className="space-y-2">
                  {res.results.map((h, n) => (
                    <li key={h.chunk_id} className="rounded-xl border border-line bg-surface-2/60 p-3">
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <p className="text-sm font-medium text-ink"><span className="mr-2 text-ink-3">{n + 1}.</span>{h.section ?? h.title}</p>
                        <span className="flex gap-1.5">
                          <Pill tone={h.score >= 0.5 ? "good" : h.score >= 0.1 ? "warning" : "neutral"} title="Cross-encoder relevance">{(h.score * 100).toFixed(0)}%</Pill>
                          <Pill title="Dense (embedding) cosine similarity">dense {h.dense_score.toFixed(2)}</Pill>
                          <Pill title="BM25 score, normalised to the best hit">bm25 {h.lexical_score.toFixed(2)}</Pill>
                        </span>
                      </div>
                      <p className="mt-0.5 text-[11px] text-ink-3">{h.title} · {h.document}</p>
                      <details className="mt-1.5">
                        <summary className="cursor-pointer text-xs text-ink-2 line-clamp-2">{h.text}</summary>
                        <p className="mt-1 whitespace-pre-wrap text-xs leading-relaxed text-ink-2">{h.text}</p>
                      </details>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          )}
        </div>
      </Card>

      <Card>
        <CardHeader title="Indexed documents" subtitle="Add .md, .txt, .pdf or .docx files to knowledge/ and rebuild with scripts/ingest_knowledge.py" />
        {!i ? <Skeleton className="m-4 h-48" /> : !i.ready ? <EmptyState message="The knowledge index has not been built yet." /> : (
          <div className="overflow-x-auto px-2 pb-3">
            <table className="w-full min-w-[800px] text-sm">
              <thead>
                <tr className="text-left text-xs text-ink-3">
                  {["Document", "Category", "Source basis", "Chunks"].map((h, n) => <th key={h} className={`px-3 py-2 font-medium ${n === 3 ? "text-right" : ""}`}>{h}</th>)}
                </tr>
              </thead>
              <tbody>
                {i.documents.map((d) => (
                  <tr key={d.file} className="border-t border-line align-top">
                    <td className="px-3 py-2.5">
                      <p className="flex items-center gap-1.5 text-ink"><BookOpenText className="h-3.5 w-3.5 text-accent" /> {d.title}</p>
                      <p className="mt-0.5 text-[11px] text-ink-3">{d.file}</p>
                    </td>
                    <td className="px-3 py-2.5"><Pill tone={d.category === "curated_qa" ? "accent" : "neutral"}>{titleCase(d.category)}</Pill></td>
                    <td className="max-w-[520px] px-3 py-2.5 text-xs text-ink-2">{d.source_basis ?? "—"}</td>
                    <td className="tabular px-3 py-2.5 text-right text-ink-2">{num(d.chunks)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
