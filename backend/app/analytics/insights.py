"""Deterministic analytical insights used by the AI Copilot.

Each function answers one class of business question with exact numbers computed in SQL/Python.
The SLM only explains these results; it never calculates them.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.analytics import breakdowns
from app.analytics.filters import AnalyticsFilters, dataset_as_of, pct
from app.analytics.kpis import ar_as_of, compute_kpis, days_in_ar
from app.models.rcm import Claim, ClaimStatus, Denial, Payer, Provider
from app.services.claims_service import prioritized_open_claims


# Claims need roughly a month to be adjudicated; rates on younger claims are incomplete and biased
# toward fast payers, so outcome-rate comparisons end this many days before the as-of date.
MATURITY_LAG_DAYS = 30


def windows(db: Session, days: int = 90, end: date | None = None,
            lag_days: int = 0) -> tuple[AnalyticsFilters, AnalyticsFilters]:
    """(current, previous) equal-length windows ending `lag_days` before `end` (default: as-of date)."""
    end = (end or dataset_as_of(db)) - timedelta(days=lag_days)
    cur = AnalyticsFilters(start_date=end - timedelta(days=days - 1), end_date=end)
    return cur, cur.previous_period()


def _adjudicated_by(db: Session, f: AnalyticsFilters, key_col, name_col, join_model, join_on) -> dict[str, dict]:
    adjudicated = Claim.status.in_(ClaimStatus.ADJUDICATED)
    rows = db.execute(
        select(key_col, name_col, func.sum(case((adjudicated, 1), else_=0)),
               func.sum(case((and_(adjudicated, Claim.was_denied), 1), else_=0)))
        .join(join_model, join_on).where(*f.conditions()).group_by(key_col, name_col)
    ).all()
    return {r[0]: {"name": r[1], "adjudicated": r[2] or 0, "denied": r[3] or 0} for r in rows}


def denial_rate_change(db: Session, days: int = 90, base: AnalyticsFilters | None = None) -> dict:
    """Why did the denial rate change? Compare two windows and attribute the change.

    The change in overall denial rate is decomposed by payer and by CARC reason: each segment's
    contribution = (its denials now / total adjudicated now) - (its denials before / total adjudicated before).
    Contributions sum to the overall change.
    """
    cur, prev = windows(db, days, lag_days=MATURITY_LAG_DAYS)
    if base:
        cur = replace(base, start_date=cur.start_date, end_date=cur.end_date)
        prev = replace(base, start_date=prev.start_date, end_date=prev.end_date)
    k_cur, k_prev = compute_kpis(db, cur), compute_kpis(db, prev)
    n_cur, n_prev = k_cur.adjudicated_claims or 1, k_prev.adjudicated_claims or 1

    by_payer_cur = _adjudicated_by(db, cur, Payer.id, Payer.name, Payer, Claim.payer_id == Payer.id)
    by_payer_prev = _adjudicated_by(db, prev, Payer.id, Payer.name, Payer, Claim.payer_id == Payer.id)
    payer_rows = []
    for pid in set(by_payer_cur) | set(by_payer_prev):
        c, p = by_payer_cur.get(pid, {}), by_payer_prev.get(pid, {})
        payer_rows.append({
            "payer": c.get("name") or p.get("name"),
            "denial_rate_now": pct(c.get("denied"), c.get("adjudicated")),
            "denial_rate_before": pct(p.get("denied"), p.get("adjudicated")),
            "denied_now": c.get("denied", 0), "denied_before": p.get("denied", 0),
            "contribution_pts": round(100 * (c.get("denied", 0) / n_cur - p.get("denied", 0) / n_prev), 2),
        })
    payer_rows.sort(key=lambda r: r["contribution_pts"], reverse=True)

    def carc_counts(f: AnalyticsFilters) -> dict[str, tuple[str, int]]:
        rows = db.execute(
            select(Denial.carc_code, Denial.description, func.count(func.distinct(Denial.claim_id)))
            .join(Claim, Denial.claim_id == Claim.id)
            .where(*f.conditions(), Claim.status.in_(ClaimStatus.ADJUDICATED))
            .group_by(Denial.carc_code, Denial.description)
        ).all()
        return {r[0]: (r[1], r[2]) for r in rows}

    rc, rp = carc_counts(cur), carc_counts(prev)
    reason_rows = []
    for code in set(rc) | set(rp):
        desc = (rc.get(code) or rp.get(code))[0]
        now, before = rc.get(code, ("", 0))[1], rp.get(code, ("", 0))[1]
        reason_rows.append({"carc": code, "description": desc, "denials_now": now, "denials_before": before,
                            "contribution_pts": round(100 * (now / n_cur - before / n_prev), 2)})
    reason_rows.sort(key=lambda r: r["contribution_pts"], reverse=True)

    return {
        "current_period": {"start": cur.start_date.isoformat(), "end": cur.end_date.isoformat()},
        "previous_period": {"start": prev.start_date.isoformat(), "end": prev.end_date.isoformat()},
        "maturity_lag_days": MATURITY_LAG_DAYS,
        "denial_rate_now": k_cur.denial_rate, "denial_rate_before": k_prev.denial_rate,
        "change_pts": round((k_cur.denial_rate or 0) - (k_prev.denial_rate or 0), 1),
        "adjudicated_now": k_cur.adjudicated_claims, "adjudicated_before": k_prev.adjudicated_claims,
        "by_payer": payer_rows, "by_reason": reason_rows,
    }


def denial_trend(db: Session, months: int = 6) -> list[dict]:
    from app.analytics.timeseries import claims_over_time

    end = dataset_as_of(db)
    start = date(end.year, end.month, 1)
    for _ in range(months - 1):
        start = date(start.year - (start.month == 1), (start.month - 2) % 12 + 1, 1)
    return [{"month": r["month"], "denial_rate": r["denial_rate"], "adjudicated": r["adjudicated"]}
            for r in claims_over_time(db, AnalyticsFilters(start_date=start, end_date=end))]


def ranking(db: Session, dimension: str, metric: str, f: AnalyticsFilters, min_volume: int = 30) -> list[dict]:
    """Rank payers or providers by a metric (denial_rate, avg_days_to_adjudicate, outstanding_ar, ...)."""
    rows = (breakdowns.payer_performance if dimension == "payer" else breakdowns.provider_performance)(db, f)
    rows = [r for r in rows if r.get("adjudicated", 0) >= min_volume and r.get(metric) is not None]
    return sorted(rows, key=lambda r: r[metric], reverse=True)


def top_denial_causes(db: Session, f: AnalyticsFilters) -> dict:
    reasons = breakdowns.denial_reasons(db, f, limit=8)
    cats = breakdowns.denial_categories(db, f)
    total = sum(c["count"] for c in cats) or 1
    preventable = db.scalar(
        select(func.count(Denial.id)).join(Claim, Denial.claim_id == Claim.id).where(*f.conditions(), Denial.preventable)
    ) or 0
    return {"reasons": reasons, "categories": cats, "total_denials": total,
            "preventable_share_pct": round(100.0 * preventable / total, 1)}


def ar_change(db: Session, days: int = 90) -> dict:
    """What is driving AR? Compare AR now vs `days` ago, by payer and by claim status."""
    end = dataset_as_of(db)
    before = end - timedelta(days=days)
    all_f = AnalyticsFilters()
    dar_now, ar_now = days_in_ar(db, end, all_f)
    dar_before, ar_before = days_in_ar(db, before, all_f)

    payer_rows = []
    for p in db.scalars(select(Payer)):
        pf = AnalyticsFilters(payer_ids=(p.id,))
        now, then = ar_as_of(db, end, pf), ar_as_of(db, before, pf)
        payer_rows.append({"payer": p.name, "ar_now": now, "ar_before": then, "change": round(now - then, 2)})
    payer_rows.sort(key=lambda r: r["change"], reverse=True)

    status_rows = [
        {"status": r[0], "claims": r[1], "balance": round(r[2] or 0, 2)}
        for r in db.execute(select(Claim.status, func.count(Claim.id), func.sum(Claim.balance))
                            .where(Claim.balance > 0.005).group_by(Claim.status)
                            .order_by(func.sum(Claim.balance).desc())).all()
    ]
    cur, prev = windows(db, days)
    speed = []
    for p in breakdowns.payer_performance(db, cur):
        before_row = next((x for x in breakdowns.payer_performance(db, prev) if x["id"] == p["id"]), None)
        speed.append({"payer": p["name"], "avg_days_to_adjudicate_now": p["avg_days_to_adjudicate"],
                      "avg_days_to_adjudicate_before": before_row["avg_days_to_adjudicate"] if before_row else None,
                      "pending_claims_now": p["pending_claims"]})
    speed.sort(key=lambda r: (r["avg_days_to_adjudicate_now"] or 0) - (r["avg_days_to_adjudicate_before"] or 0),
               reverse=True)
    return {
        "as_of": end.isoformat(), "compared_to": before.isoformat(),
        "ar_now": ar_now, "ar_before": ar_before, "ar_change": round(ar_now - ar_before, 2),
        "ar_change_pct": pct(ar_now - ar_before, ar_before),
        "days_in_ar_now": dar_now, "days_in_ar_before": dar_before,
        "by_payer": payer_rows, "open_balance_by_status": status_rows, "payer_speed": speed,
    }


def claims_to_prioritize(db: Session, f: AnalyticsFilters, limit: int = 8) -> dict:
    items = prioritized_open_claims(db, f, limit=limit)
    open_total = db.execute(
        select(func.count(Claim.id), func.sum(Claim.balance)).where(Claim.balance > 0.005, *f.entity_conditions())
    ).one()
    return {"top_claims": items, "open_claims": open_total[0], "open_balance": round(open_total[1] or 0, 2)}


def kpi_summary(db: Session, f: AnalyticsFilters) -> dict:
    cur = compute_kpis(db, f)
    prev = compute_kpis(db, f.previous_period())
    return {"period": {"start": f.start_date.isoformat(), "end": f.end_date.isoformat()},
            "current": cur.as_dict(), "previous": prev.as_dict()}


def provider_names(db: Session) -> dict[str, str]:
    return {p.id: p.name for p in db.scalars(select(Provider))}


def payer_names(db: Session) -> dict[str, str]:
    return {p.id: p.name for p in db.scalars(select(Payer))}
