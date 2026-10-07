// Thin client for the FastAPI backend. All data shown in the UI comes from these calls.

import type { Filters } from "@/types/api";

export const API_BASE = (process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export function toQuery(params: Record<string, string | number | boolean | string[] | undefined | null>): string {
  const q = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => q.append(k, x));
    else q.append(k, String(v));
  }
  const s = q.toString();
  return s ? `?${s}` : "";
}

export function filtersToParams(f: Filters) {
  return { start_date: f.start_date, end_date: f.end_date, payer_id: f.payer_id, provider_id: f.provider_id, status: f.status };
}

async function parseError(res: Response): Promise<ApiError> {
  let msg = `${res.status} ${res.statusText}`;
  try {
    const body = await res.json();
    if (typeof body.detail === "string") msg = body.detail;
    else if (Array.isArray(body.detail)) msg = body.detail.map((d: { msg: string }) => d.msg).join("; ");
  } catch {
    /* non-JSON error body */
  }
  return new ApiError(res.status, msg);
}

export async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { signal, cache: "no-store" });
  if (!res.ok) throw await parseError(res);
  return res.json() as Promise<T>;
}

export async function apiPost<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
  if (!res.ok) throw await parseError(res);
  return res.json() as Promise<T>;
}

export interface SSEEvent {
  event: string;
  data: unknown;
}

/** POST to a server-sent-events endpoint and yield parsed events as they arrive. */
export async function* postSSE(path: string, body: unknown, signal?: AbortSignal): AsyncGenerator<SSEEvent> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) throw await parseError(res);
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, idx);
      buffer = buffer.slice(idx + 2);
      let event = "message";
      const dataLines: string[] = [];
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
      }
      if (dataLines.length) yield { event, data: JSON.parse(dataLines.join("\n")) };
    }
  }
}
