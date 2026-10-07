"use client";

import { useCallback, useRef, useState } from "react";

import { postSSE } from "@/lib/api";
import type { IntentInfo, Source, Validation } from "@/types/api";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  streaming?: boolean;
  intent?: IntentInfo;
  sources?: Source[];
  grounded?: boolean;
  model?: string | null;
  data?: Record<string, unknown> | null;
  validation?: Validation;
  replacedReason?: string;
  totalMs?: number;
  error?: string;
}

export interface ChatOptions {
  use_rag: boolean;
  temperature?: number;
  max_tokens?: number;
}

const uid = () => Math.random().toString(36).slice(2);

/** Streams answers from /api/chat/stream (SSE: meta, token*, replace?, done). */
export function useChatStream() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const patch = (id: string, fn: (m: ChatMessage) => ChatMessage) =>
    setMessages((ms) => ms.map((m) => (m.id === id ? fn(m) : m)));

  const send = useCallback(
    async (text: string, options: ChatOptions) => {
      const question = text.trim();
      if (!question || busy) return;
      const history = messages
        .filter((m) => !m.error && m.content)
        .slice(-6)
        .map((m) => ({ role: m.role, content: m.content.slice(0, 4000) }));
      const userMsg: ChatMessage = { id: uid(), role: "user", content: question };
      const botId = uid();
      setMessages((ms) => [...ms, userMsg, { id: botId, role: "assistant", content: "", streaming: true }]);
      setBusy(true);
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      try {
        for await (const ev of postSSE("/api/chat/stream", { message: question, history, options }, ctrl.signal)) {
          const d = ev.data as Record<string, unknown>;
          if (ev.event === "meta") {
            patch(botId, (m) => ({
              ...m,
              intent: d.intent as IntentInfo,
              sources: d.sources as Source[],
              grounded: d.grounded as boolean,
              model: d.model as string | null,
              data: (d.data as Record<string, unknown>) ?? null,
            }));
          } else if (ev.event === "token") {
            patch(botId, (m) => ({ ...m, content: m.content + (d.text as string) }));
          } else if (ev.event === "replace") {
            patch(botId, (m) => ({
              ...m,
              content: d.text as string,
              replacedReason: d.reason as string,
              sources: (d.sources as Source[]) ?? m.sources,
            }));
          } else if (ev.event === "done") {
            const t = d.timings_ms as { total: number } | undefined;
            patch(botId, (m) => ({ ...m, streaming: false, validation: d.validation as Validation, totalMs: t?.total }));
          }
        }
      } catch (e) {
        const err = e as Error;
        patch(botId, (m) => ({
          ...m,
          streaming: false,
          error: err.name === "AbortError" ? "Stopped." : err.message || "The assistant is unavailable.",
        }));
      } finally {
        patch(botId, (m) => ({ ...m, streaming: false }));
        setBusy(false);
        abortRef.current = null;
      }
    },
    [busy, messages],
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);
  const reset = useCallback(() => setMessages([]), []);
  return { messages, busy, send, stop, reset };
}
