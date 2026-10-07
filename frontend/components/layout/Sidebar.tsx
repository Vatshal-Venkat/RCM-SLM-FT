"use client";

import clsx from "clsx";
import {
  BarChart3, Bot, BookOpenText, Cpu, FileText, LayoutDashboard, Menu, Settings, ShieldX, Sparkles, X,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { useApi } from "@/hooks/useApi";
import type { Health } from "@/types/api";

const NAV = [
  { href: "/", label: "Dashboard", icon: LayoutDashboard },
  { href: "/copilot", label: "AI Copilot", icon: Bot },
  { href: "/claims", label: "Claims", icon: FileText },
  { href: "/denials", label: "Denials", icon: ShieldX },
  { href: "/analytics", label: "Analytics", icon: BarChart3 },
  { href: "/knowledge", label: "RCM Knowledge", icon: BookOpenText },
  { href: "/model", label: "Model", icon: Cpu },
  { href: "/settings", label: "Settings", icon: Settings },
];

function HealthDot() {
  const { data, error } = useApi<Health>("/health");
  const ok = data?.status === "ok" && data.components.rag.ready;
  const label = error ? "Backend offline" : !data ? "Connecting…" : ok ? "AI services online" : "Degraded";
  return (
    <div className="flex items-center gap-2 text-xs text-ink-3">
      <span className={clsx("h-2 w-2 rounded-full", error ? "bg-critical" : ok ? "bg-good" : "bg-warning")} aria-hidden />
      {label}
    </div>
  );
}

export function Sidebar() {
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const isActive = (href: string) => (href === "/" ? pathname === "/" : pathname.startsWith(href));

  const nav = (
    <nav className="flex flex-1 flex-col gap-1 px-3">
      {NAV.map(({ href, label, icon: Icon }) => (
        <Link
          key={href}
          href={href}
          onClick={() => setOpen(false)}
          className={clsx(
            "group flex items-center gap-3 rounded-xl px-3 py-2 text-sm transition-colors",
            isActive(href) ? "bg-accent/15 text-ink ring-1 ring-inset ring-accent/30" : "text-ink-2 hover:bg-white/5 hover:text-ink",
          )}
        >
          <Icon className={clsx("h-4 w-4", isActive(href) ? "text-accent" : "text-ink-3 group-hover:text-ink-2")} />
          {label}
        </Link>
      ))}
    </nav>
  );

  const brand = (
    <Link href="/" className="flex items-center gap-2.5 px-5 py-5">
      <span className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-accent to-accent-2 shadow-lg shadow-accent/20">
        <Sparkles className="h-4.5 w-4.5 text-white" />
      </span>
      <span className="leading-tight">
        <span className="block text-sm font-semibold text-ink">RCM Intelligence</span>
        <span className="block text-[11px] text-ink-3">AI Revenue Cycle Platform</span>
      </span>
    </Link>
  );

  return (
    <>
      <div className="sticky top-0 z-30 flex items-center justify-between border-b border-line bg-page/80 px-4 py-3 backdrop-blur lg:hidden">
        <Link href="/" className="flex items-center gap-2 text-sm font-semibold"><Sparkles className="h-4 w-4 text-accent" /> RCM Intelligence</Link>
        <button aria-label="Open navigation" onClick={() => setOpen(true)} className="rounded-lg p-1.5 hover:bg-white/5"><Menu className="h-5 w-5" /></button>
      </div>

      {open && (
        <div className="fixed inset-0 z-40 lg:hidden" role="dialog" aria-modal="true">
          <div className="absolute inset-0 bg-black/60" onClick={() => setOpen(false)} />
          <aside className="glass absolute inset-y-0 left-0 flex w-72 flex-col pb-5">
            <div className="flex items-center justify-between pr-3">{brand}
              <button aria-label="Close navigation" onClick={() => setOpen(false)} className="rounded-lg p-1.5 hover:bg-white/5"><X className="h-5 w-5" /></button>
            </div>
            {nav}
            <div className="px-6 pt-4"><HealthDot /></div>
          </aside>
        </div>
      )}

      <aside className="sticky top-0 hidden h-screen w-64 shrink-0 flex-col border-r border-line bg-surface-1/60 pb-5 backdrop-blur lg:flex">
        {brand}
        {nav}
        <div className="mx-3 mt-4 rounded-xl border border-line bg-white/[0.02] p-3">
          <HealthDot />
          <p className="mt-1.5 text-[11px] leading-relaxed text-ink-3">Local SLM · RAG · Deterministic analytics · Validation</p>
        </div>
      </aside>
    </>
  );
}
