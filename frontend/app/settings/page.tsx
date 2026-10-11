"use client";

import { CheckCircle2, RotateCcw } from "lucide-react";
import { useState } from "react";

import { useFilterOptions } from "@/components/dashboard/FilterBar";
import { Card, CardHeader, PageHeader, Pill } from "@/components/ui/primitives";
import { useApi } from "@/hooks/useApi";
import { API_BASE } from "@/lib/api";
import { type CopilotPrefs, DEFAULT_PREFS, savePrefs, usePrefs } from "@/lib/preferences";
import type { Health } from "@/types/api";

const inputCls = "h-9 w-32 rounded-lg border border-line bg-surface-2 px-2.5 text-sm text-ink outline-none focus:border-accent/60 focus:ring-2 focus:ring-accent/20";

export default function SettingsPage() {
  const health = useApi<Health>("/health");
  const opts = useFilterOptions();
  const saved = usePrefs();
  // Edits stay local until saved; null = untouched, showing the saved value.
  const [edit, setEdit] = useState<CopilotPrefs | null>(null);
  const [flash, setFlash] = useState(false);
  const p = edit ?? saved;

  const save = (next: CopilotPrefs) => {
    savePrefs(next);
    setEdit(null);
    setFlash(true);
    setTimeout(() => setFlash(false), 2000);
  };
  const numOrNull = (v: string, lo: number, hi: number) => (v === "" ? null : Math.min(hi, Math.max(lo, Number(v))));

  return (
    <div className="mx-auto max-w-[900px]">
      <PageHeader eyebrow="Settings" title="Settings" description="Backend connection and Copilot preferences." />

      <Card className="mb-4">
        <CardHeader title="Backend connection" />
        <dl className="space-y-2 px-5 pb-5 text-sm">
          <Row label="API base URL"><code className="text-xs text-ink">{API_BASE}</code></Row>
          <Row label="Status">
            {health.error ? <Pill tone="critical">Offline · {health.error}</Pill>
              : !health.data ? <Pill>Checking…</Pill>
              : <Pill tone={health.data.status === "ok" ? "good" : "warning"}>{health.data.status === "ok" ? "Online" : "Degraded"} · {health.data.app}</Pill>}
          </Row>
          <Row label="Dataset">{opts.data ? `As of ${opts.data.as_of} · ${opts.data.payers.length} payers · ${opts.data.providers.length} providers` : "—"}</Row>
          {opts.data?.data_notice && <Row label="Notice"><span className="text-xs text-ink-2">{opts.data.data_notice}</span></Row>}
        </dl>
        <p className="px-5 pb-4 text-[11px] text-ink-3">Set <code>NEXT_PUBLIC_API_BASE_URL</code> in <code>frontend/.env.local</code> to point at a different backend.</p>
      </Card>

      <Card>
        <CardHeader title="Copilot preferences" subtitle="Saved in this browser. Empty fields use the backend defaults." />
        <form className="space-y-4 px-5 pb-5 text-sm" onSubmit={(e) => { e.preventDefault(); save(p); }}>
          <label className="flex items-center justify-between gap-4">
            <span>
              <span className="text-ink">Ground answers in the knowledge base</span>
              <span className="block text-xs text-ink-3">Default for the toggle under the chat box. Turning it off is only useful for comparing against the bare model.</span>
            </span>
            <input type="checkbox" checked={p.useRag} onChange={(e) => setEdit({ ...p, useRag: e.target.checked })} className="h-4 w-4 accent-[var(--accent)]" />
          </label>
          <label className="flex items-center justify-between gap-4">
            <span>
              <span className="text-ink">Temperature</span>
              <span className="block text-xs text-ink-3">0–1.5. Lower gives more consistent, literal answers.</span>
            </span>
            <input type="number" min={0} max={1.5} step={0.05} placeholder="default" className={inputCls}
              value={p.temperature ?? ""} onChange={(e) => setEdit({ ...p, temperature: numOrNull(e.target.value, 0, 1.5) })} />
          </label>
          <label className="flex items-center justify-between gap-4">
            <span>
              <span className="text-ink">Max answer tokens</span>
              <span className="block text-xs text-ink-3">16–1024. Longer answers take proportionally longer on CPU.</span>
            </span>
            <input type="number" min={16} max={1024} step={16} placeholder="default" className={inputCls}
              value={p.maxTokens ?? ""} onChange={(e) => setEdit({ ...p, maxTokens: numOrNull(e.target.value, 16, 1024) })} />
          </label>
          <div className="flex items-center gap-3 border-t border-line pt-4">
            <button type="submit" disabled={!edit} className="rounded-lg bg-accent px-4 py-1.5 text-sm font-medium text-white hover:bg-accent/85 disabled:opacity-40">Save</button>
            <button type="button" onClick={() => save(DEFAULT_PREFS)} className="inline-flex items-center gap-1 text-xs text-ink-2 hover:text-ink">
              <RotateCcw className="h-3.5 w-3.5" /> Reset to defaults
            </button>
            {flash && <span className="inline-flex items-center gap-1 text-xs text-good"><CheckCircle2 className="h-3.5 w-3.5" /> Saved</span>}
          </div>
        </form>
      </Card>
    </div>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b border-line py-1.5">
      <dt className="text-ink-3">{label}</dt>
      <dd className="text-right">{children}</dd>
    </div>
  );
}
