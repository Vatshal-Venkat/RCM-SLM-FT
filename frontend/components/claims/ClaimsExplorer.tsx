"use client";

import { ArrowDown, ArrowUp, ChevronLeft, ChevronRight, Search } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useState } from "react";

import { DEFAULT_FILTERS, FilterBar, type FilterState, toApiFilters, useFilterOptions } from "@/components/dashboard/FilterBar";
import { Card, EmptyState, ErrorState, PageHeader, Skeleton, StatusBadge } from "@/components/ui/primitives";
import { useApi } from "@/hooks/useApi";
import { filtersToParams, toQuery } from "@/lib/api";
import { dateLabel, num, titleCase, usd } from "@/lib/format";
import type { ClaimList } from "@/types/api";

const PAGE_SIZE = 25;

export const DENIAL_CATEGORIES = [
  "authorization", "coding", "coordination_of_benefits", "documentation", "duplicate", "eligibility",
  "medical_necessity", "missing_information", "timely_filing",
];

type SortKey = "claim_date" | "service_date" | "billed_amount" | "paid_amount" | "balance" | "status";

const COLUMNS: { label: string; sort?: SortKey; right?: boolean }[] = [
  { label: "Claim" }, { label: "Submitted", sort: "claim_date" }, { label: "Service", sort: "service_date" },
  { label: "Payer" }, { label: "Provider" }, { label: "CPT" },
  { label: "Billed", sort: "billed_amount", right: true }, { label: "Paid", sort: "paid_amount", right: true },
  { label: "Balance", sort: "balance", right: true }, { label: "Status", sort: "status" }, { label: "Denial" },
  { label: "Days in AR", right: true },
];

const inputCls = "h-9 rounded-lg border border-line bg-surface-2 px-2.5 text-sm text-ink outline-none focus:border-accent/60 focus:ring-2 focus:ring-accent/20";

export function ClaimsExplorer() {
  const params = useSearchParams();
  const opts = useFilterOptions();
  const [filters, setFilters] = useState<FilterState>(() => ({
    ...DEFAULT_FILTERS,
    // Links from other pages (e.g. Denials) usually mean "all time"; keep their filter visible.
    preset: params.get("denial_category") || params.get("status") ? "365" : DEFAULT_FILTERS.preset,
    status: params.get("status") ?? "",
    payer: params.get("payer") ?? "",
  }));
  const [category, setCategory] = useState(params.get("denial_category") ?? "");
  const [openOnly, setOpenOnly] = useState(false);
  const [draft, setDraft] = useState("");
  const [search, setSearch] = useState("");
  const [sort, setSort] = useState<{ key: SortKey; order: "asc" | "desc" }>({ key: "claim_date", order: "desc" });
  const [page, setPage] = useState(1);

  // Search as you type, without a request per keystroke.
  useEffect(() => {
    const t = setTimeout(() => {
      setSearch(draft.trim());
      setPage(1);
    }, 300);
    return () => clearTimeout(t);
  }, [draft]);

  const path = opts.data
    ? `/api/claims${toQuery({
      ...filtersToParams(toApiFilters(filters, opts.data.as_of)),
      search: search || undefined, denial_category: category || undefined, open_only: openOnly || undefined,
      sort: sort.key, order: sort.order, page, page_size: PAGE_SIZE,
    })}`
    : null;
  const { data, error, loading, reload } = useApi<ClaimList>(path);

  const pages = data ? Math.max(1, Math.ceil(data.total / PAGE_SIZE)) : 1;
  const toggleSort = (key: SortKey) => {
    setSort((s) => ({ key, order: s.key === key && s.order === "desc" ? "asc" : "desc" }));
    setPage(1);
  };

  return (
    <div className="mx-auto max-w-[1400px]">
      <PageHeader eyebrow="Claims" title="Claims explorer"
        description="Every claim in the synthetic dataset, filterable by period, payer, provider, status and denial category. Open a claim for its full history and an AI analysis." />

      <FilterBar value={filters} onChange={(v) => { setFilters(v); setPage(1); }} options={opts.data} />

      <div className="mb-4 flex flex-wrap items-center gap-2">
        <label className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-ink-3" aria-hidden />
          <input value={draft} onChange={(e) => setDraft(e.target.value.replace(/[^A-Za-z0-9.\- ]/g, "").slice(0, 40))}
            placeholder="Claim ID, CPT, ICD-10 or CARC…" aria-label="Search claims" className={`${inputCls} w-64 pl-8`} />
        </label>
        <select aria-label="Denial category" className={inputCls} value={category}
          onChange={(e) => { setCategory(e.target.value); setPage(1); }}>
          <option value="">All denial categories</option>
          {DENIAL_CATEGORIES.map((c) => <option key={c} value={c}>{titleCase(c)}</option>)}
        </select>
        <label className="inline-flex items-center gap-1.5 text-sm text-ink-2">
          <input type="checkbox" checked={openOnly} onChange={(e) => { setOpenOnly(e.target.checked); setPage(1); }}
            className="accent-[var(--accent)]" />
          Open balance only
        </label>
        {data && <span className="ml-auto text-xs text-ink-3">{num(data.total)} claims</span>}
      </div>

      {(error || opts.error) && <ErrorState message={error || opts.error || ""} onRetry={() => { opts.reload(); reload(); }} />}

      <Card>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[1100px] text-sm">
            <thead>
              <tr className="text-left text-xs text-ink-3">
                {COLUMNS.map((c) => (
                  <th key={c.label} className={`px-3 py-2.5 font-medium ${c.right ? "text-right" : ""}`}>
                    {c.sort ? (
                      <button onClick={() => toggleSort(c.sort!)} className="inline-flex items-center gap-1 hover:text-ink">
                        {c.label}
                        {sort.key === c.sort && (sort.order === "desc" ? <ArrowDown className="h-3 w-3" /> : <ArrowUp className="h-3 w-3" />)}
                      </button>
                    ) : c.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className={`tabular transition-opacity ${loading ? "opacity-60" : ""}`}>
              {data?.items.map((c) => (
                <tr key={c.claim_id} className="border-t border-line hover:bg-white/[0.02]">
                  <td className="px-3 py-2"><Link href={`/claims/${c.claim_id}`} className="font-medium text-accent hover:underline">{c.claim_id}</Link></td>
                  <td className="px-3 py-2 text-ink-2">{dateLabel(c.claim_date)}</td>
                  <td className="px-3 py-2 text-ink-2">{dateLabel(c.service_date)}</td>
                  <td className="max-w-[180px] truncate px-3 py-2 text-ink-2" title={c.payer}>{c.payer}</td>
                  <td className="max-w-[180px] truncate px-3 py-2 text-ink-2" title={c.provider}>{c.provider}</td>
                  <td className="px-3 py-2 text-ink-2">{c.cpt_code}</td>
                  <td className="px-3 py-2 text-right text-ink-2">{usd(c.billed_amount, true)}</td>
                  <td className="px-3 py-2 text-right text-ink-2">{usd(c.paid_amount, true)}</td>
                  <td className={`px-3 py-2 text-right ${c.balance > 0.005 ? "text-ink" : "text-ink-3"}`}>{usd(c.balance, true)}</td>
                  <td className="px-3 py-2"><StatusBadge status={c.status} /></td>
                  <td className="px-3 py-2 text-xs text-ink-2">{c.denial_reason_code ? `CARC ${c.denial_reason_code} · ${titleCase(c.denial_category)}` : "—"}</td>
                  <td className="px-3 py-2 text-right text-ink-2">{c.days_in_ar}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {!data && loading && <div className="space-y-2 p-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-8" />)}</div>}
          {data && data.items.length === 0 && <EmptyState message="No claims match these filters." />}
        </div>
        {data && data.total > 0 && (
          <div className="flex items-center justify-between border-t border-line px-4 py-3 text-xs text-ink-3">
            <span>
              {num((page - 1) * PAGE_SIZE + 1)}–{num(Math.min(page * PAGE_SIZE, data.total))} of {num(data.total)} · data as of {data.as_of}
            </span>
            <span className="flex items-center gap-2">
              <button disabled={page <= 1} onClick={() => setPage(page - 1)} aria-label="Previous page"
                className="rounded-lg p-1.5 hover:bg-white/5 disabled:opacity-30"><ChevronLeft className="h-4 w-4" /></button>
              Page {page} of {num(pages)}
              <button disabled={page >= pages} onClick={() => setPage(page + 1)} aria-label="Next page"
                className="rounded-lg p-1.5 hover:bg-white/5 disabled:opacity-30"><ChevronRight className="h-4 w-4" /></button>
            </span>
          </div>
        )}
      </Card>
    </div>
  );
}
