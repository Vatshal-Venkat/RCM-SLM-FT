"use client";

import clsx from "clsx";
import { ArrowUp, Bot, Database, ListChecks, RotateCcw, Square, User } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Collapsible, DataView, ExplainIcons, IssuesList, SourcesList, ValidationBadge } from "@/components/chat/Explain";
import { Card, Pill } from "@/components/ui/primitives";
import { type ChatMessage, useChatStream } from "@/hooks/useChatStream";
import { titleCase } from "@/lib/format";

// Mirrors the backend's chat_max_message_chars.
const MAX_CHARS = 2000;

const SUGGESTIONS: { group: string; prompts: string[] }[] = [
  { group: "Your data", prompts: ["Why did our denial rate increase?", "Which payer has the highest denial rate?", "Which claims should we prioritize?"] },
  { group: "RCM knowledge", prompts: ["What is the difference between an ERA and an EOB?", "How is Days in AR calculated?", "Should a rejected claim be appealed?"] },
];

const INTENT_LABELS: Record<string, string> = {
  rcm_knowledge: "Knowledge",
  kpi_analytics: "Analytics",
  claim_specific: "Claim",
  data_query: "Data query",
};

export function CopilotChat() {
  const { messages, busy, send, stop, reset } = useChatStream();
  const [draft, setDraft] = useState("");
  const [useRag, setUseRag] = useState(true);
  const params = useSearchParams();
  const router = useRouter();
  const autoSent = useRef(false);
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  const submit = (text: string) => {
    const q = text.trim();
    if (!q || busy || q.length > MAX_CHARS) return;
    setDraft("");
    void send(q, { use_rag: useRag });
  };

  // Questions linked from the dashboard arrive as /copilot?q=...; ask once, then drop the
  // parameter so a refresh does not ask again.
  useEffect(() => {
    const q = params.get("q");
    if (!q || autoSent.current) return;
    autoSent.current = true;
    void send(q.slice(0, MAX_CHARS), { use_rag: true });
    router.replace("/copilot");
  }, [params, router, send]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages]);

  return (
    <Card className="flex h-[calc(100vh-13rem)] min-h-[520px] flex-col overflow-hidden">
      <div className="flex-1 overflow-y-auto px-4 py-5 sm:px-6" aria-live="polite">
        {messages.length === 0 ? (
          <EmptyChat onPick={submit} />
        ) : (
          <div className="mx-auto max-w-3xl space-y-6">
            {messages.map((m) => (m.role === "user" ? <UserBubble key={m.id} m={m} /> : <AssistantMessage key={m.id} m={m} />))}
            <div ref={endRef} />
          </div>
        )}
      </div>

      <div className="border-t border-line bg-surface-1/60 px-4 py-3 sm:px-6">
        <form
          className="mx-auto max-w-3xl"
          onSubmit={(e) => {
            e.preventDefault();
            submit(draft);
          }}
        >
          <div className="flex items-end gap-2 rounded-2xl border border-line-strong bg-surface-2 p-2 focus-within:border-accent/50">
            <textarea
              ref={inputRef}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                  e.preventDefault();
                  submit(draft);
                }
              }}
              rows={Math.min(6, Math.max(1, draft.split("\n").length))}
              placeholder="Ask about claims, denials, KPIs or RCM concepts…"
              aria-label="Message the RCM Copilot"
              className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-ink placeholder:text-ink-3 focus:outline-none"
            />
            {busy ? (
              <button type="button" onClick={stop} aria-label="Stop generating"
                className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white/10 text-ink hover:bg-white/15">
                <Square className="h-4 w-4" />
              </button>
            ) : (
              <button type="submit" aria-label="Send" disabled={!draft.trim() || draft.length > MAX_CHARS}
                className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-accent text-white transition hover:bg-accent/85 disabled:cursor-not-allowed disabled:opacity-40">
                <ArrowUp className="h-4 w-4" />
              </button>
            )}
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-ink-3">
            <label className="inline-flex cursor-pointer items-center gap-1.5">
              <input type="checkbox" checked={useRag} onChange={(e) => setUseRag(e.target.checked)} className="accent-[var(--accent)]" />
              Ground answers in the RCM knowledge base
            </label>
            <span className="flex items-center gap-3">
              <span className={clsx("tabular", draft.length > MAX_CHARS && "text-critical")}>{draft.length}/{MAX_CHARS}</span>
              {messages.length > 0 && (
                <button type="button" onClick={() => { stop(); reset(); inputRef.current?.focus(); }}
                  className="inline-flex items-center gap-1 hover:text-ink">
                  <RotateCcw className="h-3 w-3" /> New chat
                </button>
              )}
            </span>
          </div>
        </form>
      </div>
    </Card>
  );
}

function EmptyChat({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="mx-auto flex max-w-2xl flex-col items-center py-8 text-center">
      <span className="grid h-12 w-12 place-items-center rounded-2xl bg-gradient-to-br from-accent to-accent-2 shadow-lg shadow-accent/20">
        <Bot className="h-6 w-6 text-white" />
      </span>
      <h2 className="mt-4 text-lg font-semibold text-ink">How can I help with your revenue cycle?</h2>
      <p className="mt-1 text-sm text-ink-3">
        Figures come from your claims data, definitions from the validated knowledge base, and every answer is checked
        before you see it.
      </p>
      <div className="mt-6 grid w-full gap-4 text-left sm:grid-cols-2">
        {SUGGESTIONS.map((s) => (
          <div key={s.group}>
            <p className="mb-2 text-xs font-medium text-ink-3">{s.group}</p>
            <div className="grid gap-2">
              {s.prompts.map((q) => (
                <button key={q} onClick={() => onPick(q)}
                  className="rounded-xl border border-line bg-surface-2/70 px-3 py-2 text-left text-sm text-ink-2 transition hover:border-accent/40 hover:text-ink">
                  {q}
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function UserBubble({ m }: { m: ChatMessage }) {
  return (
    <div className="flex justify-end gap-3">
      <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-tr-md bg-accent/15 px-4 py-2.5 text-sm text-ink ring-1 ring-inset ring-accent/25">
        {m.content}
      </p>
      <span className="mt-1 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-white/5 text-ink-3"><User className="h-4 w-4" /></span>
    </div>
  );
}

function AssistantMessage({ m }: { m: ChatMessage }) {
  const done = !m.streaming;
  const n = m.sources?.length ?? 0;
  return (
    <div className="flex gap-3">
      <span className="mt-1 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-gradient-to-br from-accent to-accent-2 text-white">
        <Bot className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1">
        {m.content ? (
          <div className="prose-rcm text-sm text-ink-2">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
          </div>
        ) : m.streaming ? (
          <p className="flex h-6 items-center gap-1" aria-label="Generating answer">
            {[0, 1, 2].map((i) => <span key={i} className="typing-dot h-1.5 w-1.5 rounded-full bg-ink-3" />)}
          </p>
        ) : null}

        {m.error && <p className="mt-2 text-sm text-critical">{m.error}</p>}

        {done && m.replacedReason && (
          <p className="mt-2 text-[11px] text-ink-3">Answer revised after validation: {m.replacedReason}</p>
        )}

        {(m.intent || m.validation) && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <ValidationBadge v={m.validation} />
            {m.intent && INTENT_LABELS[m.intent.intent] && <Pill tone="accent">{INTENT_LABELS[m.intent.intent]}</Pill>}
            {m.grounded && (
              <Pill title="Answer was generated from retrieved knowledge and/or computed data">
                {m.data ? <Database className="h-3 w-3" /> : <ExplainIcons.BookOpen className="h-3 w-3" />}
                Grounded{n ? ` · ${n} source${n > 1 ? "s" : ""}` : ""}
              </Pill>
            )}
            {done && m.totalMs !== undefined && <span className="tabular text-[11px] text-ink-3">{(m.totalMs / 1000).toFixed(1)}s</span>}
            {m.model && <span className="text-[11px] text-ink-3">· {m.model}</span>}
          </div>
        )}

        {done && (m.data || n > 0 || m.validation) && (
          <div className="mt-3 space-y-2">
            {m.data && hasDataView(m.data) && (
              <Collapsible title={`Data behind this answer · ${titleCase(m.data.type as string)}`} icon={<Database className="h-3.5 w-3.5" />} defaultOpen>
                <DataView data={m.data} />
              </Collapsible>
            )}
            {n > 0 && (
              <Collapsible title={`Sources (${n})`} icon={<ExplainIcons.BookOpen className="h-3.5 w-3.5" />}>
                <SourcesList sources={m.sources!} />
              </Collapsible>
            )}
            {m.validation && (
              <Collapsible title="Validation details" icon={<ListChecks className="h-3.5 w-3.5" />}>
                <IssuesList v={m.validation} />
              </Collapsible>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function hasDataView(data: Record<string, unknown>): boolean {
  const t = data.type;
  return ["ranking", "denial_drivers", "ar_drivers", "prioritization", "denial_causes", "kpi_summary"].includes(t as string)
    || (t === "claim" && Boolean(data.found));
}
