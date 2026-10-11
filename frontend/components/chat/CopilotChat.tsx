"use client";

import clsx from "clsx";
import {
  ArrowDown, ArrowUp, BarChart3, BookOpen, Check, Copy, Cpu, Database, Hash, ListChecks, Loader2, RotateCcw,
  ShieldCheck, Sparkles, Square, type LucideIcon,
} from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { AnswerBody } from "@/components/chat/AnswerBody";
import { DataView, IssuesList, SourcesList, ValidationBadge } from "@/components/chat/Explain";
import { Card, Pill } from "@/components/ui/primitives";
import { useApi } from "@/hooks/useApi";
import { type ChatMessage, type ChatOptions, useChatStream } from "@/hooks/useChatStream";
import { titleCase } from "@/lib/format";
import { type CopilotPrefs, getPrefs, usePrefs } from "@/lib/preferences";
import type { Health } from "@/types/api";

// Mirrors the backend's chat_max_message_chars.
const MAX_CHARS = 2000;

const SUGGESTIONS: { group: string; icon: LucideIcon; prompts: string[] }[] = [
  { group: "Your numbers", icon: BarChart3, prompts: ["Why did our denial rate increase?", "Which payer has the highest denial rate?"] },
  { group: "Work queue", icon: ListChecks, prompts: ["Which claims should we prioritize?", "What is causing our AR to increase?"] },
  { group: "Codes", icon: Hash, prompts: ["What does CO-16 mean?", "When should modifier 25 be used?"] },
  { group: "RCM knowledge", icon: BookOpen, prompts: ["What is the difference between an ERA and an EOB?", "Should a rejected claim be appealed?"] },
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
  const prefs = usePrefs();
  // The toggle starts from the Settings default; a change here applies to this chat only.
  const [ragOverride, setRagOverride] = useState<boolean | null>(null);
  const useRag = ragOverride ?? prefs.useRag;
  const params = useSearchParams();
  const router = useRouter();
  const autoSent = useRef(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  // Follow the stream only while the reader is at the bottom; a new question always scrolls.
  const stick = useRef(true);
  const prevCount = useRef(0);
  const [showJump, setShowJump] = useState(false);

  const submit = (text: string) => {
    const q = text.trim();
    if (!q || busy || q.length > MAX_CHARS) return;
    setDraft("");
    void send(q, chatOptions(prefs, useRag));
  };

  // Questions linked from the dashboard arrive as /copilot?q=...; ask once, then drop the
  // parameter so a refresh does not ask again. Preferences are read directly: on first render
  // the hook still holds the server defaults.
  useEffect(() => {
    const q = params.get("q");
    if (!q || autoSent.current) return;
    autoSent.current = true;
    const p = getPrefs();
    void send(q.slice(0, MAX_CHARS), chatOptions(p, p.useRag));
    router.replace("/copilot");
  }, [params, router, send]);

  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    const grew = messages.length > prevCount.current;
    prevCount.current = messages.length;
    if (grew) {
      stick.current = true;
      el.scrollTo({ top: el.scrollHeight, behavior: "smooth" });
    } else if (messages.at(-1)?.streaming && stick.current) {
      el.scrollTop = el.scrollHeight;
    }
    // A finished answer is not scrolled: its evidence opens below it and the answer stays in view.
  }, [messages]);

  const onScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    stick.current = atBottom;
    setShowJump(!atBottom && messages.length > 0);
  };

  const jumpToLatest = () => {
    stick.current = true;
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  };

  const newChat = () => {
    stop();
    reset();
    setShowJump(false);
    inputRef.current?.focus();
  };

  const lastAssistant = messages.findLast((m) => m.role === "assistant")?.id;

  return (
    <Card className="flex h-[calc(100dvh-57px-3rem)] min-h-[520px] flex-col overflow-hidden lg:h-[calc(100dvh-4rem)]">
      <ChatHeader onNewChat={messages.length ? newChat : undefined} />

      <div className="relative min-h-0 flex-1">
        <div ref={scrollRef} onScroll={onScroll} className="h-full overflow-y-auto px-4 py-6 sm:px-6" aria-live="polite">
          {messages.length === 0 ? (
            <EmptyChat onPick={submit} />
          ) : (
            <div className="mx-auto max-w-3xl space-y-8">
              {messages.map((m, i) => (m.role === "user"
                ? <UserBubble key={m.id} m={m} />
                : <AssistantMessage key={m.id} m={m} isLast={m.id === lastAssistant} busy={busy}
                    question={messages[i - 1]?.role === "user" ? messages[i - 1].content : undefined} onAsk={submit} />))}
            </div>
          )}
        </div>
        {showJump && (
          <button type="button" onClick={jumpToLatest}
            className="absolute bottom-3 left-1/2 inline-flex -translate-x-1/2 items-center gap-1.5 rounded-full border border-line-strong bg-surface-3/95 px-3 py-1.5 text-xs text-ink shadow-lg backdrop-blur hover:bg-surface-3">
            <ArrowDown className="h-3.5 w-3.5" /> Jump to latest
          </button>
        )}
      </div>

      <div className="border-t border-line bg-surface-1/70 px-4 pt-3 pb-3 sm:px-6">
        <form className="mx-auto max-w-3xl" onSubmit={(e) => { e.preventDefault(); submit(draft); }}>
          <div className="flex items-end gap-2 rounded-2xl border border-line-strong bg-surface-2 p-2 shadow-[0_8px_30px_-12px_rgba(0,0,0,0.6)] transition focus-within:border-accent/60 focus-within:shadow-[0_0_0_4px_rgba(124,140,255,0.12)]">
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
              placeholder="Ask about claims, codes or KPIs…"
              aria-label="Message the RCM Copilot"
              className="max-h-40 flex-1 resize-none bg-transparent px-2 py-1.5 text-sm text-ink placeholder:text-ink-3 focus:outline-none"
            />
            {busy ? (
              <button type="button" onClick={stop} aria-label="Stop generating" title="Stop"
                className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-white/10 text-ink hover:bg-white/15">
                <Square className="h-3.5 w-3.5 fill-current" />
              </button>
            ) : (
              <button type="submit" aria-label="Send" disabled={!draft.trim() || draft.length > MAX_CHARS}
                className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-accent to-[#6a7cff] text-white shadow-md shadow-accent/30 transition hover:brightness-110 disabled:cursor-not-allowed disabled:opacity-35 disabled:shadow-none">
                <ArrowUp className="h-4 w-4" />
              </button>
            )}
          </div>
          <div className="mt-2 flex flex-wrap items-center justify-between gap-2 px-1 text-[11px] text-ink-3">
            <Switch checked={useRag} onChange={setRagOverride} label="Ground answers in the RCM knowledge base" />
            <span className="flex items-center gap-3">
              {draft.length > MAX_CHARS * 0.8 && (
                <span className={clsx("tabular", draft.length > MAX_CHARS && "text-critical")}>{draft.length}/{MAX_CHARS}</span>
              )}
              <span className="hidden sm:inline"><Kbd>Enter</Kbd> to send · <Kbd>Shift</Kbd> + <Kbd>Enter</Kbd> new line</span>
            </span>
          </div>
        </form>
      </div>
    </Card>
  );
}

function ChatHeader({ onNewChat }: { onNewChat?: () => void }) {
  const { data, error } = useApi<Health>("/health");
  const ready = data?.components.llm.ready;
  const status = error ? "Backend offline" : !data ? "Connecting…" : ready ? "Local model ready" : "Model not loaded";
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-accent to-accent-2 shadow-lg shadow-accent/20">
          <Sparkles className="h-4.5 w-4.5 text-white" />
        </span>
        <div className="min-w-0">
          <h1 className="text-sm font-semibold text-ink">RCM Copilot</h1>
          <p className="flex items-center gap-1.5 truncate text-[11px] text-ink-3">
            <span className={clsx("h-1.5 w-1.5 shrink-0 rounded-full", error ? "bg-critical" : ready ? "bg-good" : "bg-warning")} aria-hidden />
            {status}<span className="hidden sm:inline"> · runs on this machine · every answer validated</span>
          </p>
        </div>
      </div>
      {onNewChat && (
        <button type="button" onClick={onNewChat}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-xs text-ink-2 transition hover:border-line-strong hover:bg-white/5 hover:text-ink">
          <RotateCcw className="h-3.5 w-3.5" /> New chat
        </button>
      )}
    </div>
  );
}

function EmptyChat({ onPick }: { onPick: (q: string) => void }) {
  const trust: [LucideIcon, string][] = [
    [Cpu, "Runs locally: claim data never leaves this machine"],
    [Database, "Figures computed from your claims data"],
    [ShieldCheck, "Every answer checked before you see it"],
  ];
  return (
    <div className="mx-auto flex min-h-full max-w-3xl flex-col justify-center py-4 animate-fade-up">
      <div className="text-center">
        <span className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-accent to-accent-2 shadow-xl shadow-accent/25">
          <Sparkles className="h-7 w-7 text-white" />
        </span>
        <h2 className="mt-5 text-2xl font-semibold tracking-tight text-ink">
          How can I help with your <span className="gradient-text">revenue cycle</span>?
        </h2>
        <p className="mx-auto mt-2 max-w-xl text-sm text-ink-2">
          Ask about denials, codes, claims or KPIs. Answers cite their sources and show the data behind them.
        </p>
      </div>

      <div className="mt-8 grid gap-3 sm:grid-cols-2">
        {SUGGESTIONS.map(({ group, icon: Icon, prompts }) => (
          <div key={group} className="rounded-2xl border border-line bg-white/[0.02] p-3">
            <p className="mb-2 flex items-center gap-1.5 px-1 text-[11px] font-semibold uppercase tracking-wide text-ink-3">
              <Icon className="h-3.5 w-3.5 text-accent-2" aria-hidden /> {group}
            </p>
            <div className="grid gap-1.5">
              {prompts.map((q) => (
                <button key={q} type="button" onClick={() => onPick(q)}
                  className="group flex items-center justify-between gap-2 rounded-xl px-2.5 py-2 text-left text-sm text-ink-2 transition hover:bg-white/[0.05] hover:text-ink">
                  {q}
                  <ArrowUp className="h-3.5 w-3.5 shrink-0 rotate-45 text-ink-3 opacity-0 transition group-hover:opacity-100" aria-hidden />
                </button>
              ))}
            </div>
          </div>
        ))}
      </div>

      <ul className="mt-6 flex flex-wrap justify-center gap-x-5 gap-y-2 text-[11px] text-ink-3">
        {trust.map(([Icon, label]) => (
          <li key={label} className="flex items-center gap-1.5"><Icon className="h-3.5 w-3.5 text-good" aria-hidden />{label}</li>
        ))}
      </ul>
    </div>
  );
}

function UserBubble({ m }: { m: ChatMessage }) {
  return (
    <div className="flex justify-end animate-fade-up">
      <p className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-md bg-gradient-to-br from-accent/25 to-accent/10 px-4 py-2.5 text-sm text-ink ring-1 ring-inset ring-accent/30">
        {m.content}
      </p>
    </div>
  );
}

type Tab = "data" | "sources" | "checks";

function AssistantMessage({ m, isLast, busy, question, onAsk }: {
  m: ChatMessage; isLast: boolean; busy: boolean; question?: string; onAsk: (q: string) => void;
}) {
  const done = !m.streaming;
  const n = m.sources?.length ?? 0;
  const hasData = Boolean(m.data && hasDataView(m.data));
  // null = automatic (data opens by default for analytics answers); "none" = the reader closed it.
  const [tab, setTab] = useState<Tab | "none" | null>(null);
  const [highlight, setHighlight] = useState<number | null>(null);
  const [copied, setCopied] = useState(false);
  const active: Tab | null = tab === "none" ? null : tab ?? (hasData ? "data" : null);

  const cite = (ref: number) => {
    setTab("sources");
    setHighlight(ref);
    setTimeout(() => document.getElementById(`${m.id}-source-${ref}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" }), 60);
  };
  const copy = async () => {
    await navigator.clipboard.writeText(m.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const tabs: { key: Tab; label: string; icon: LucideIcon; show: boolean }[] = [
    { key: "data", label: m.data ? `Data · ${titleCase(String(m.data.type))}` : "Data", icon: Database, show: hasData },
    { key: "sources", label: `Sources (${n})`, icon: BookOpen, show: n > 0 },
    { key: "checks", label: "Checks", icon: ShieldCheck, show: Boolean(m.validation) },
  ];
  const suggestions = isLast && done && !m.error ? followUps(m) : [];
  const revised = m.replacedReason && m.replacedReason !== "cleaned formatting";

  return (
    <div className="flex gap-3 animate-fade-up">
      <span className="mt-0.5 hidden h-8 w-8 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-accent to-accent-2 text-white shadow-md shadow-accent/20 sm:grid">
        <Sparkles className="h-4 w-4" />
      </span>
      <div className="min-w-0 flex-1">
        {m.streaming && <Progress m={m} />}

        {m.content && (
          <div className={clsx(m.streaming && "mt-3")}>
            <AnswerBody text={m.content} sourceCount={n} onCite={cite} streaming={m.streaming} />
          </div>
        )}

        {m.error && <p className="mt-2 rounded-xl border border-red-400/20 bg-red-500/5 px-3 py-2 text-sm text-critical">{m.error}</p>}

        {done && (m.intent || m.validation) && (
          <div className="mt-3 flex flex-wrap items-center gap-1.5">
            <ValidationBadge v={m.validation} />
            {m.intent && INTENT_LABELS[m.intent.intent] && <Pill tone="accent">{INTENT_LABELS[m.intent.intent]}</Pill>}
            {revised && <Pill title={m.replacedReason}><ShieldCheck className="h-3 w-3" /> Corrected after checks</Pill>}
            {m.totalMs !== undefined && (
              <span className="tabular text-[11px] text-ink-3" title={m.model ?? undefined}>{(m.totalMs / 1000).toFixed(1)}s</span>
            )}
            <span className="ml-auto flex items-center gap-0.5">
              <IconButton label={copied ? "Copied" : "Copy answer"} onClick={copy}>
                {copied ? <Check className="h-3.5 w-3.5 text-good" /> : <Copy className="h-3.5 w-3.5" />}
              </IconButton>
              {question && (
                <IconButton label="Ask again" onClick={() => onAsk(question)} disabled={busy}><RotateCcw className="h-3.5 w-3.5" /></IconButton>
              )}
            </span>
          </div>
        )}

        {done && tabs.some((t) => t.show) && (
          <div className="mt-3 overflow-hidden rounded-xl border border-line">
            <div className="flex flex-wrap gap-1 bg-white/[0.02] p-1" role="tablist">
              {tabs.filter((t) => t.show).map(({ key, label, icon: Icon }) => (
                <button key={key} type="button" role="tab" aria-selected={active === key}
                  onClick={() => setTab(active === key ? "none" : key)}
                  className={clsx("inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-xs font-medium transition",
                    active === key ? "bg-surface-3 text-ink shadow-sm" : "text-ink-3 hover:bg-white/5 hover:text-ink-2")}>
                  <Icon className="h-3.5 w-3.5" aria-hidden /> {label}
                </button>
              ))}
            </div>
            {active && (
              <div className="max-h-80 overflow-y-auto border-t border-line p-3" role="tabpanel">
                {active === "data" && m.data && <DataView data={m.data} />}
                {active === "sources" && <SourcesList sources={m.sources ?? []} highlight={highlight} idPrefix={`${m.id}-source`} />}
                {active === "checks" && <IssuesList v={m.validation} />}
              </div>
            )}
          </div>
        )}

        {suggestions.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-2">
            {suggestions.map((q) => (
              <button key={q} type="button" onClick={() => onAsk(q)} disabled={busy}
                className="rounded-full border border-line px-3 py-1.5 text-xs text-ink-2 transition hover:border-accent/50 hover:bg-accent/10 hover:text-ink disabled:opacity-40">
                {q}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/** Live pipeline steps while an answer is generated, driven by the stream's own events. */
function Progress({ m }: { m: ChatMessage }) {
  const now = useNow(Boolean(m.streaming));
  const elapsed = now && m.startedAt ? Math.max(0, Math.round((now - m.startedAt) / 1000)) : 0;
  // Tokens stop while the backend validates (and, if needed, regenerates) the answer.
  const checking = m.phase === "writing" && Boolean(now && m.lastTokenAt && now - m.lastTokenAt > 1200);
  const codes = m.sources?.some((s) => s.document === "code_reference.yaml");
  const evidence = m.phase === "routing" ? "Gathering evidence"
    : m.data ? "Computed figures from claims data"
    : codes ? "Looked up the code reference"
    : m.sources?.length ? `Found ${m.sources.length} knowledge source${m.sources.length > 1 ? "s" : ""}`
    : "Gathering evidence";
  const order = ["routing", "evidence", "writing", "checking"];
  const at = order.indexOf(checking ? "checking" : m.phase ?? "routing");
  const steps = [
    m.intent ? `Understood: ${INTENT_LABELS[m.intent.intent] ?? "question"}` : "Understanding the question",
    evidence,
    "Writing the answer",
    "Checking facts, numbers and codes",
  ];
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 rounded-xl border border-line bg-white/[0.02] px-3 py-2 text-[11px]">
      {steps.map((label, i) => (
        <span key={i} className={clsx("flex items-center gap-1.5", i < at ? "text-ink-2" : i === at ? "text-ink" : "text-ink-3/60")}>
          {i < at ? <Check className="h-3 w-3 text-good" aria-hidden />
            : i === at ? <Loader2 className="h-3 w-3 animate-spin text-accent" aria-hidden />
            : <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />}
          {label}
        </span>
      ))}
      <span className="tabular ml-auto text-ink-3">{elapsed}s</span>
    </div>
  );
}

function useNow(active: boolean): number {
  const [now, setNow] = useState(0);
  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => setNow(Date.now()), 500);
    return () => clearInterval(t);
  }, [active]);
  return now;
}

function Switch({ checked, onChange, label }: { checked: boolean; onChange: (v: boolean) => void; label: string }) {
  return (
    <button type="button" role="switch" aria-checked={checked} onClick={() => onChange(!checked)}
      className="inline-flex items-center gap-2 text-ink-3 transition hover:text-ink-2">
      <span className={clsx("relative h-4 w-7 shrink-0 rounded-full transition-colors", checked ? "bg-accent" : "bg-white/15")}>
        <span className={clsx("absolute top-0.5 left-0.5 h-3 w-3 rounded-full bg-white shadow transition-transform", checked && "translate-x-3")} />
      </span>
      {label}
    </button>
  );
}

function IconButton({ label, onClick, disabled, children }: {
  label: string; onClick: () => void; disabled?: boolean; children: React.ReactNode;
}) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} aria-label={label} title={label}
      className="grid h-7 w-7 place-items-center rounded-lg text-ink-3 transition hover:bg-white/5 hover:text-ink disabled:opacity-40">
      {children}
    </button>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return <kbd className="rounded border border-line-strong bg-white/5 px-1 py-px font-sans text-[10px] text-ink-2">{children}</kbd>;
}

/** Follow-up questions that the analytics engine answers, chosen from the answer's own data. */
function followUps(m: ChatMessage): string[] {
  const d = m.data;
  switch (d?.type) {
    case "kpi_summary": return ["Why did our denial rate increase?", "Which payer has the highest denial rate?"];
    case "denial_drivers": return ["What are our most common denial reasons?", "Which claims should we prioritize?"];
    case "ranking": return ["Why did our denial rate increase?", "What is causing our AR to increase?"];
    case "denial_causes": return ["What does CO-197 mean?", "Which claims should we prioritize?"];
    case "ar_drivers": return ["Which payer has the most outstanding AR?", "Which claims should we prioritize?"];
    case "prioritization": {
      const id = (d.top_claims as { claim_id: string }[] | undefined)?.[0]?.claim_id;
      return id ? [`Why was claim ${id} denied?`, "Why did our denial rate increase?"] : [];
    }
    case "claim": {
      const carc = (d.findings as { title: string }[] | undefined)?.[0]?.title.match(/CARC (\w+)/)?.[1];
      return [...(carc ? [`What does CARC ${carc} mean?`] : []), "Which claims should we prioritize?"];
    }
  }
  const terms = m.intent?.terms ?? [];
  if (terms.some((t) => t.startsWith("carc") || t.startsWith("group_") || t === "denial" || t === "denial_rate")) {
    return ["What are our most common denial reasons?", "Why did our denial rate increase?"];
  }
  if (terms.some((t) => t === "days_in_ar" || t === "ar")) return ["What is causing our AR to increase?"];
  return [];
}

function chatOptions(p: CopilotPrefs, useRag: boolean): ChatOptions {
  return { use_rag: useRag, temperature: p.temperature ?? undefined, max_tokens: p.maxTokens ?? undefined };
}

function hasDataView(data: Record<string, unknown>): boolean {
  const t = data.type;
  return ["ranking", "denial_drivers", "ar_drivers", "prioritization", "denial_causes", "kpi_summary"].includes(t as string)
    || (t === "claim" && Boolean(data.found));
}
