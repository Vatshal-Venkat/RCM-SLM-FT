import clsx from "clsx";
import { AlertTriangle, CheckCircle2, Info, OctagonAlert, RefreshCw } from "lucide-react";
import type { ReactNode } from "react";

export function Card({ className, children }: { className?: string; children: ReactNode }) {
  return <div className={clsx("glass rounded-2xl", className)}>{children}</div>;
}

export function CardHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 px-5 pt-4 pb-2">
      <div className="min-w-0">
        <h3 className="text-sm font-semibold text-ink">{title}</h3>
        {subtitle && <p className="mt-0.5 text-xs text-ink-3">{subtitle}</p>}
      </div>
      {right}
    </div>
  );
}

export function PageHeader({ eyebrow, title, description, right }: {
  eyebrow?: string; title: ReactNode; description?: ReactNode; right?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4 animate-fade-up">
      <div className="min-w-0">
        {eyebrow && <p className="text-xs font-medium uppercase tracking-[0.18em] text-accent-2">{eyebrow}</p>}
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-ink md:text-3xl">{title}</h1>
        {description && <p className="mt-1.5 max-w-3xl text-sm text-ink-2">{description}</p>}
      </div>
      {right}
    </div>
  );
}

const STATUS_STYLES: Record<string, string> = {
  paid: "bg-emerald-500/12 text-emerald-300 ring-emerald-400/25",
  partially_paid: "bg-teal-500/12 text-teal-300 ring-teal-400/25",
  pending: "bg-sky-500/12 text-sky-300 ring-sky-400/25",
  denied: "bg-red-500/12 text-red-300 ring-red-400/25",
  rejected: "bg-orange-500/12 text-orange-300 ring-orange-400/25",
  appealed: "bg-violet-500/12 text-violet-300 ring-violet-400/25",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={clsx("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset",
      STATUS_STYLES[status] ?? "bg-white/5 text-ink-2 ring-white/10")}>
      {status.replace(/_/g, " ")}
    </span>
  );
}

export function Pill({ children, tone = "neutral", title }: {
  children: ReactNode; tone?: "neutral" | "accent" | "good" | "warning" | "critical"; title?: string;
}) {
  const tones = {
    neutral: "bg-white/5 text-ink-2 ring-white/10",
    accent: "bg-accent/12 text-[#b9c2ff] ring-accent/30",
    good: "bg-emerald-500/12 text-emerald-300 ring-emerald-400/25",
    warning: "bg-amber-500/12 text-amber-300 ring-amber-400/25",
    critical: "bg-red-500/12 text-red-300 ring-red-400/25",
  };
  return (
    <span title={title} className={clsx("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium ring-1 ring-inset", tones[tone])}>
      {children}
    </span>
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={clsx("animate-pulse rounded-lg bg-white/[0.04]", className)} />;
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded-xl border border-red-400/20 bg-red-500/5 p-6 text-center">
      <OctagonAlert className="h-5 w-5 text-critical" aria-hidden />
      <p className="text-sm text-ink-2">{message}</p>
      {onRetry && (
        <button onClick={onRetry} className="inline-flex items-center gap-1.5 rounded-lg bg-white/5 px-3 py-1.5 text-xs text-ink hover:bg-white/10">
          <RefreshCw className="h-3.5 w-3.5" /> Retry
        </button>
      )}
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return <p className="px-5 py-10 text-center text-sm text-ink-3">{message}</p>;
}

/** Severity with icon + label (status colours never carry meaning alone). */
export function SeverityTag({ severity }: { severity: "high" | "medium" | "low" | "info" | "error" | "warning" }) {
  const map = {
    high: { icon: OctagonAlert, cls: "text-critical", label: "High" },
    error: { icon: OctagonAlert, cls: "text-critical", label: "Error" },
    medium: { icon: AlertTriangle, cls: "text-warning", label: "Medium" },
    warning: { icon: AlertTriangle, cls: "text-warning", label: "Warning" },
    low: { icon: Info, cls: "text-sky-300", label: "Low" },
    info: { icon: CheckCircle2, cls: "text-ink-3", label: "Info" },
  }[severity];
  const Icon = map.icon;
  return (
    <span className={clsx("inline-flex items-center gap-1 text-[11px] font-semibold uppercase tracking-wide", map.cls)}>
      <Icon className="h-3.5 w-3.5" aria-hidden /> {map.label}
    </span>
  );
}
