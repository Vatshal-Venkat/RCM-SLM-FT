"use client";

import {
  Activity, AlertTriangle, ArrowRightCircle, BookOpen, FileText, Info, Lightbulb, ListChecks, Quote, TrendingUp,
  type LucideIcon,
} from "lucide-react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

// Section labels the backend's answer formats ask the model for (app/ai/prompts.py).
const SECTIONS: Record<string, LucideIcon> = {
  "answer": Info,
  "why it matters": Lightbulb,
  "example": Quote,
  "key drivers": TrendingUp,
  "details": FileText,
  "recommended action": ArrowRightCircle,
  "recommended actions": ListChecks,
  "recommended next action": ArrowRightCircle,
  "claim summary": FileText,
  "current status": Activity,
  "potential issue": AlertTriangle,
  "explanation": BookOpen,
};

const LABEL_RE = new RegExp(
  String.raw`^[ \t]*(?:\*\*)?(${Object.keys(SECTIONS).sort((a, b) => b.length - a.length).join("|")}):(?:\*\*)?[ \t]*`,
  "gim",
);

interface Section { label: string | null; body: string }

/** Split "**Answer:** … **Why it matters:** …" into labelled sections (works on partial, streaming text). */
export function splitSections(text: string): Section[] {
  const matches = [...text.matchAll(LABEL_RE)];
  if (!matches.length) return [{ label: null, body: text }];
  const out: Section[] = [];
  const lead = text.slice(0, matches[0].index).trim();
  if (lead) out.push({ label: null, body: lead });
  matches.forEach((m, i) => {
    const end = i + 1 < matches.length ? matches[i + 1].index : text.length;
    out.push({ label: m[1].toLowerCase(), body: text.slice(m.index! + m[0].length, end).trim() });
  });
  return out;
}

/** Remove trailing "Sources: [1], [2]" / "Source: DATA" lines: sources are attached separately. */
export function cleanAnswer(text: string): string {
  return text.replace(/^[ \t]*(?:\*\*)?sources?:(?:\*\*)?.*$/gim, "").trim();
}

/** Turn inline [n] citations into links the renderer shows as chips. */
function linkCitations(md: string, maxRef: number): string {
  return md.replace(/\[(\d{1,2})\](?!\()/g, (all, n) => (Number(n) >= 1 && Number(n) <= maxRef ? `[${n}](#cite-${n})` : all));
}

export function AnswerBody({ text, sourceCount, onCite, streaming }: {
  text: string; sourceCount: number; onCite: (ref: number) => void; streaming?: boolean;
}) {
  const components: Components = {
    a: ({ href, children }) => {
      const m = href?.match(/^#cite-(\d+)$/);
      if (m) {
        return (
          <button type="button" onClick={() => onCite(Number(m[1]))} title={`Show source ${m[1]}`}
            className="mx-0.5 inline-grid h-4 min-w-4 place-items-center rounded bg-accent/20 px-1 align-[1px] text-[10px] font-semibold text-[#c7ceff] hover:bg-accent/35">
            {children}
          </button>
        );
      }
      return <a href={href} target="_blank" rel="noreferrer" className="text-accent underline-offset-2 hover:underline">{children}</a>;
    },
  };
  const md = (s: string) => <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{linkCitations(s, sourceCount)}</ReactMarkdown>;
  const sections = splitSections(cleanAnswer(text));

  return (
    <div className="space-y-3">
      {sections.map((s, i) => {
        const isLead = s.label === null || s.label === "answer";
        const Icon = s.label ? SECTIONS[s.label] : null;
        const last = i === sections.length - 1;
        if (!s.body && !(streaming && last)) return null;
        if (isLead) {
          return (
            <div key={i} className="prose-rcm text-[15px] leading-relaxed text-ink">
              {md(s.body)}
              {streaming && last && <span className="stream-caret" aria-hidden />}
            </div>
          );
        }
        return (
          <section key={i} className="rounded-xl border border-line bg-white/[0.02] px-3.5 py-2.5">
            <h4 className="mb-1 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-ink-3">
              {Icon && <Icon className="h-3.5 w-3.5 text-accent-2" aria-hidden />}
              {s.label}
            </h4>
            <div className="prose-rcm text-sm text-ink-2">
              {md(s.body)}
              {streaming && last && <span className="stream-caret" aria-hidden />}
            </div>
          </section>
        );
      })}
    </div>
  );
}
