"""Copilot data grounding: route an analytics question to a deterministic insight and render
an exact fact sheet for the SLM.

    question -> (deterministic) question type + entities + time window
             -> SQL insight function -> DataContext(text for the model, payload for the UI)

Numbers in the fact sheet are pre-formatted exactly as the model should quote them, and any
derived figure (changes, shares, contributions) is computed here so the model never does math.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import timedelta

from sqlalchemy.orm import Session

from app.ai.intent import Intent, IntentResult
from app.analytics import insights
from app.analytics.filters import AnalyticsFilters, dataset_as_of
from app.db.session import get_sessionmaker
from app.services.chat_service import DataContext

PAYER_ALIASES = {
    "PYR-MCR": ["medicare part b", "medicare ffs", "original medicare", "traditional medicare"],
    "PYR-MCD": ["medicaid"],
    "PYR-NWH": ["northwind"],
    "PYR-COB": ["cobalt"],
    "PYR-LSH": ["lakeshore", "medicare advantage"],
    "PYR-STC": ["sterling"],
}
PROVIDER_ALIASES = {
    "PRV-01": ["riverside", "family medicine"], "PRV-02": ["summit", "orthopedic"],
    "PRV-03": ["harborview", "cardiology"], "PRV-04": ["clearwater", "imaging", "radiology"],
    "PRV-05": ["maple grove", "pediatric"], "PRV-06": ["northgate", "physical therapy"],
    "PRV-07": ["lakeside", "dermatology"], "PRV-08": ["valley", "behavioral"],
}


def _usd(x: float | None) -> str:
    return "n/a" if x is None else f"${x:,.0f}"


def _p(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1f}%"


def _d(x: float | None) -> str:
    return "n/a" if x is None else f"{x:.1f} days"


def _signed(x: float, unit: str = " pts") -> str:
    return f"{x:+.1f}{unit}"


def detect_entities(q: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
    ql = q.lower()
    payers = tuple(pid for pid, al in PAYER_ALIASES.items() if any(a in ql for a in al))
    # "medicare advantage" should not also select Medicare Part B.
    if "PYR-LSH" in payers and "medicare advantage" in ql and not any(a in ql for a in PAYER_ALIASES["PYR-MCR"]):
        payers = tuple(p for p in payers if p != "PYR-MCR")
    providers = tuple(pid for pid, al in PROVIDER_ALIASES.items() if any(a in ql for a in al))
    return payers, providers


def detect_window_days(q: str, default: int = 90) -> int:
    ql = q.lower()
    m = re.search(r"last (\d{1,3}) (day|week|month)s?", ql)
    if m:
        n, unit = int(m.group(1)), m.group(2)
        return max(7, min(730, n * {"day": 1, "week": 7, "month": 30}[unit]))
    for pat, days in [(r"\b(this|last|past) month\b", 30), (r"\b(this|last|past) quarter\b", 90),
                      (r"\b(this|last|past) (6|six) months\b", 182), (r"\b(this|last|past) year\b", 365),
                      (r"\bytd\b|year to date", 270)]:
        if re.search(pat, ql):
            return days
    return default


class AnalyticsContextProvider:
    """Implements `DataContextProvider` for the chat service."""

    def build(self, intent: IntentResult, question: str) -> DataContext | None:
        with get_sessionmaker()() as db:
            if intent.intent == Intent.CLAIM_SPECIFIC and intent.entities.get("claim_ids"):
                return self._claim(db, intent.entities["claim_ids"][0])
            return self._analytics(db, question)

    # ------------------------------------------------------------------ routing
    def _analytics(self, db: Session, q: str) -> DataContext:
        ql = q.lower()
        payers, providers = detect_entities(q)
        days = detect_window_days(q)
        end = dataset_as_of(db)
        base = AnalyticsFilters(start_date=end - timedelta(days=days - 1), end_date=end,
                                payer_ids=payers, provider_ids=providers)

        if re.search(r"priorit|work first|follow.?up first|which claims should", ql):
            return self._prioritize(db, base)
        if re.search(r"\b(a/?r|accounts receivable|days in ar)\b", ql) and re.search(r"increas|grow|rising|caus|driv|why|up\b", ql):
            return self._ar_drivers(db, days)
        if re.search(r"denial", ql) and re.search(r"increas|rise|rising|went up|go up|grow|why did|spike|jump|chang", ql):
            return self._denial_drivers(db, days, base)
        if re.search(r"(highest|lowest|worst|best|most|least|rank|compare|top)", ql) and re.search(r"payer|payor|insur|provider|practice|clinic", ql):
            dim = "provider" if re.search(r"provider|practice|clinic", ql) else "payer"
            metric = ("avg_days_to_adjudicate" if re.search(r"slow|days to (pay|adjudicat)|fast", ql)
                      else "outstanding_ar" if re.search(r"\bar\b|receivable|outstanding", ql)
                      else "clean_claim_rate" if "clean" in ql
                      else "denial_rate")
            lowest = bool(re.search(r"lowest|best|least", ql)) != (metric == "clean_claim_rate")
            return self._ranking(db, dim, metric, replace(base, start_date=end - timedelta(days=max(days, 180) - 1)), lowest)
        if re.search(r"(cause|reason|driver|why).*(denial|denied)|denial.*(cause|reason)|top denial", ql):
            return self._denial_causes(db, replace(base, start_date=end - timedelta(days=max(days, 180) - 1)))
        return self._kpi_summary(db, base)

    # ------------------------------------------------------------------ fact sheets
    def _denial_drivers(self, db: Session, days: int, base: AnalyticsFilters) -> DataContext:
        r = insights.denial_rate_change(db, days, AnalyticsFilters(payer_ids=base.payer_ids, provider_ids=base.provider_ids))
        trend = insights.denial_trend(db, months=6)
        change = r["change_pts"]
        direction = "increased" if change > 0.2 else "decreased" if change < -0.2 else "was essentially unchanged"
        top_payer, top_reason = r["by_payer"][0], r["by_reason"][0]
        findings = [
            f"The denial rate {direction}: {_p(r['denial_rate_before'])} -> {_p(r['denial_rate_now'])} ({_signed(change)}).",
        ]
        if change > 0.2:
            findings += [
                f"The largest payer driver is {top_payer['payer']}: its denial rate went from "
                f"{_p(top_payer['denial_rate_before'])} to {_p(top_payer['denial_rate_now'])}, adding "
                f"{_signed(top_payer['contribution_pts'])} to the overall rate.",
                f"The largest reason driver is CARC {top_reason['carc']} ({top_reason['description']}): "
                f"{top_reason['denials_before']} -> {top_reason['denials_now']} denials ({_signed(top_reason['contribution_pts'])}).",
            ]
        lines = [
            "KEY FINDINGS (state these first):", *[f"{i + 1}. {s}" for i, s in enumerate(findings)],
            f"Direction: the denial rate {direction}.",
            f"Periods compared: claims submitted {r['previous_period']['start']} to {r['previous_period']['end']} vs "
            f"{r['current_period']['start']} to {r['current_period']['end']} (claims from the last "
            f"{r['maturity_lag_days']} days are excluded because most are not yet adjudicated).",
            "Monthly denial rate: " + "; ".join(f"{t['month']} {_p(t['denial_rate'])}" for t in trend) + ".",
            "Payer contributions (percentage points of the overall change):",
            *[f"- {x['payer']}: {_p(x['denial_rate_before'])} -> {_p(x['denial_rate_now'])}, {_signed(x['contribution_pts'])}"
              for x in r["by_payer"][:3]],
            "Denial reason contributions:",
            *[f"- CARC {x['carc']} ({x['description']}): {x['denials_before']} -> {x['denials_now']}, "
              f"{_signed(x['contribution_pts'])}" for x in r["by_reason"][:3]],
        ]
        return DataContext("\n".join(lines), {"type": "denial_drivers", **r, "trend": trend})

    def _ar_drivers(self, db: Session, days: int) -> DataContext:
        r = insights.ar_change(db, days)
        direction = "increased" if r["ar_change"] > 0 else "decreased"
        top_payer = r["by_payer"][0]
        slow = r["payer_speed"][0]
        biggest_status = r["open_balance_by_status"][0]
        findings = [
            f"Outstanding AR {direction} from {_usd(r['ar_before'])} to {_usd(r['ar_now'])} ({_p(r['ar_change_pct'])}); "
            f"Days in AR moved from {_d(r['days_in_ar_before'])} to {_d(r['days_in_ar_now'])}.",
            f"{top_payer['payer']} accounts for the largest AR increase: {_usd(top_payer['ar_before'])} -> "
            f"{_usd(top_payer['ar_now'])} ({_usd(top_payer['change'])}).",
            f"{slow['payer']} slowed adjudication from {_d(slow['avg_days_to_adjudicate_before'])} to "
            f"{_d(slow['avg_days_to_adjudicate_now'])} and has {slow['pending_claims_now']} claims pending.",
            f"The largest open balance is in {biggest_status['status']} claims: {biggest_status['claims']} claims, "
            f"{_usd(biggest_status['balance'])}.",
        ]
        lines = [
            "KEY FINDINGS (state these first):", *[f"{i + 1}. {s}" for i, s in enumerate(findings)],
            f"Direction: outstanding AR {direction}.",
            f"Period: {r['compared_to']} to {r['as_of']}.",
            "AR change by payer:",
            *[f"- {x['payer']}: {_usd(x['ar_before'])} -> {_usd(x['ar_now'])} ({_usd(x['change'])})" for x in r["by_payer"][:4]],
            "Average days from submission to adjudication (previous -> current):",
            *[f"- {x['payer']}: {_d(x['avg_days_to_adjudicate_before'])} -> {_d(x['avg_days_to_adjudicate_now'])}"
              for x in r["payer_speed"][:3]],
            "Open balance by claim status:",
            *[f"- {x['status']}: {x['claims']} claims, {_usd(x['balance'])}" for x in r["open_balance_by_status"]],
        ]
        return DataContext("\n".join(lines), {"type": "ar_drivers", **r})

    def _ranking(self, db: Session, dim: str, metric: str, f: AnalyticsFilters, lowest: bool) -> DataContext:
        rows = insights.ranking(db, dim, metric, f)
        if lowest:
            rows = list(reversed(rows))
        fmt = {"denial_rate": _p, "clean_claim_rate": _p, "avg_days_to_adjudicate": _d, "outstanding_ar": _usd}[metric]
        label = metric.replace("_", " ")
        if not rows:
            return DataContext(f"No {dim}s have enough adjudicated claims in this period to rank.", {"type": "ranking", "rows": []})
        top = rows[0]
        lines = [
            "KEY FINDINGS (state these first):",
            f"1. {top['name']} has the {'lowest' if lowest else 'highest'} {label}: {fmt(top[metric])}.",
            f"Ranking of {dim}s by {label} ({'lowest' if lowest else 'highest'} first), claims submitted "
            f"{f.start_date} to {f.end_date}:",
            *[f"{i + 1}. {r['name']}: {label} {fmt(r[metric])} ({r['denied']} denied of {r['adjudicated']} adjudicated; "
              f"outstanding AR {_usd(r['outstanding_ar'])})" for i, r in enumerate(rows)],
        ]
        return DataContext("\n".join(lines), {"type": "ranking", "dimension": dim, "metric": metric,
                                              "lowest_first": lowest, "rows": rows,
                                              "period": {"start": f.start_date.isoformat(), "end": f.end_date.isoformat()}})

    def _denial_causes(self, db: Session, f: AnalyticsFilters) -> DataContext:
        r = insights.top_denial_causes(db, f)
        top_cat, top_reason = (r["categories"] or [None])[0], (r["reasons"] or [None])[0]
        lines = [
            "KEY FINDINGS (state these first):",
            *([f"1. The largest denial category is {top_cat['category'].replace('_', ' ')}: {top_cat['count']} denials "
               f"({_p(top_cat['share_pct'])})."] if top_cat else []),
            *([f"2. The most frequent reason is CARC {top_reason['carc_code']} ({top_reason['description']}): "
               f"{top_reason['count']} denials."] if top_reason else []),
            f"3. {_p(r['preventable_share_pct'])} of denials were preventable.",
            f"Period: claims submitted {f.start_date} to {f.end_date}.",
            f"Total denials: {r['total_denials']}; preventable share: {_p(r['preventable_share_pct'])}.",
            "Denial categories:",
            *[f"- {c['category'].replace('_', ' ')}: {c['count']} denials ({_p(c['share_pct'])}), {_usd(c['denied_amount'])}"
              for c in r["categories"][:6]],
            "Top CARC reasons:",
            *[f"- CARC {x['carc_code']} {x['description']}: {x['count']} denials ({_p(x['share_pct'])})"
              for x in r["reasons"][:5]],
        ]
        return DataContext("\n".join(lines), {"type": "denial_causes", **r,
                                              "period": {"start": f.start_date.isoformat(), "end": f.end_date.isoformat()}})

    def _prioritize(self, db: Session, f: AnalyticsFilters) -> DataContext:
        r = insights.claims_to_prioritize(db, f)
        top = r["top_claims"][:3]
        lines = [
            "KEY FINDINGS (state these first):",
            f"1. Work these claims first: {', '.join(c['claim_id'] for c in top)}.",
            f"2. There are {r['open_claims']} open claims with an open balance of {_usd(r['open_balance'])}.",
            "Priority score combines balance, unresolved denial/rejection, recoverability, deadline risk and age.",
            "Top claims to work first:",
            *[f"{i + 1}. {c['claim_id']} ({c['payer']}, {c['status']}, balance {_usd(c['balance'])}, "
              f"age {c['age_days']} days): {'; '.join(c['reasons']) or 'routine follow-up'}"
              for i, c in enumerate(r["top_claims"][:6])],
        ]
        return DataContext("\n".join(lines), {"type": "prioritization", **r})

    def _kpi_summary(self, db: Session, f: AnalyticsFilters) -> DataContext:
        r = insights.kpi_summary(db, f)
        c, p = r["current"], r["previous"]
        lines = [f"Question type: KPI summary, claims submitted {f.start_date} to {f.end_date} (vs previous equal period)."]
        for key, label, fmt in [("total_claims", "Total claims", str), ("denial_rate", "Denial rate", _p),
                                ("clean_claim_rate", "Clean claim rate", _p),
                                ("first_pass_resolution_rate", "First pass resolution rate", _p),
                                ("days_in_ar", "Days in AR", _d), ("net_collection_rate", "Net collection rate", _p),
                                ("outstanding_ar", "Outstanding AR", _usd), ("total_paid", "Cash collected", _usd)]:
            lines.append(f"- {label}: {fmt(c[key])} (previous {fmt(p[key])})")
        return DataContext("\n".join(lines), {"type": "kpi_summary", **r})

    def _claim(self, db: Session, claim_id: str) -> DataContext | None:
        from app.services.claim_analysis import analyze_claim_facts

        facts = analyze_claim_facts(db, claim_id)
        if facts is None:
            return DataContext(f"Claim {claim_id} was not found in the claims database.", {"type": "claim", "found": False})
        return DataContext(facts.fact_sheet, {"type": "claim", "found": True, "claim_id": claim_id,
                                              "findings": [f.__dict__ for f in facts.findings]},
                           retrieval_query=facts.retrieval_query)
