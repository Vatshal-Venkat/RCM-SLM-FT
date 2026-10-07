"""Monthly time series for charts."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.analytics.filters import AnalyticsFilters, month_bucket, pct, resolve_period
from app.analytics.kpis import days_in_ar
from app.models.rcm import Claim, ClaimStatus, Denial, Payment


def month_ends(start: date, end: date) -> list[tuple[str, date]]:
    out, cur = [], date(start.year, start.month, 1)
    while cur <= end:
        nxt = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
        out.append((cur.strftime("%Y-%m"), min(nxt - timedelta(days=1), end)))
        cur = nxt
    return out


def claims_over_time(db: Session, f: AnalyticsFilters) -> list[dict]:
    f = resolve_period(db, f, default_days=365)
    m = month_bucket(db, Claim.claim_date)
    adjudicated = Claim.status.in_(ClaimStatus.ADJUDICATED)
    rows = db.execute(
        select(
            m.label("month"),
            func.count(Claim.id),
            func.sum(Claim.billed_amount),
            func.sum(case((adjudicated, 1), else_=0)),
            func.sum(case((and_(adjudicated, Claim.was_denied), 1), else_=0)),
            func.sum(case((Claim.was_rejected, 1), else_=0)),
            func.sum(case((and_(adjudicated, Claim.first_pass_paid), 1), else_=0)),
        ).where(*f.conditions()).group_by(m).order_by(m)
    ).all()
    return [
        {"month": r[0], "claims": r[1], "billed": round(r[2] or 0, 2), "adjudicated": r[3], "denied": r[4],
         "rejected": r[5], "denial_rate": pct(r[4], r[3]), "clean_claim_rate": pct(r[1] - r[5], r[1]),
         "first_pass_resolution_rate": pct(r[6], r[3])}
        for r in rows
    ]


def payments_over_time(db: Session, f: AnalyticsFilters) -> list[dict]:
    """Cash by payment month (not claim month) for claims matching the entity filters."""
    f = resolve_period(db, f, default_days=365)
    m = month_bucket(db, Payment.payment_date)
    rows = db.execute(
        select(
            m.label("month"),
            func.sum(case((Payment.source == "payer", Payment.amount), else_=0)),
            func.sum(case((Payment.source == "patient", Payment.amount), else_=0)),
            func.count(Payment.id),
        ).join(Claim, Payment.claim_id == Claim.id)
        .where(Payment.payment_date >= f.start_date, Payment.payment_date <= f.end_date, *f.entity_conditions())
        .group_by(m).order_by(m)
    ).all()
    return [{"month": r[0], "payer_paid": round(r[1] or 0, 2), "patient_paid": round(r[2] or 0, 2),
             "total_paid": round((r[1] or 0) + (r[2] or 0), 2), "payments": r[3]} for r in rows]


def denials_over_time(db: Session, f: AnalyticsFilters) -> list[dict]:
    f = resolve_period(db, f, default_days=365)
    m = month_bucket(db, Denial.denial_date)
    rows = db.execute(
        select(m.label("month"), func.count(Denial.id), func.sum(Denial.denied_amount),
               func.sum(case((Denial.preventable, 1), else_=0)))
        .join(Claim, Denial.claim_id == Claim.id)
        .where(Denial.denial_date >= f.start_date, Denial.denial_date <= f.end_date, *f.entity_conditions())
        .group_by(m).order_by(m)
    ).all()
    rates = {r["month"]: r["denial_rate"] for r in claims_over_time(db, f)}
    return [{"month": r[0], "denials": r[1], "denied_amount": round(r[2] or 0, 2), "preventable": r[3],
             "denial_rate": rates.get(r[0])} for r in rows]


def ar_over_time(db: Session, f: AnalyticsFilters) -> list[dict]:
    """Outstanding AR and Days in AR at each month end."""
    f = resolve_period(db, f, default_days=365)
    out = []
    for month, month_end in month_ends(f.start_date, f.end_date):
        dar, ar = days_in_ar(db, month_end, f)
        out.append({"month": month, "as_of": month_end.isoformat(), "outstanding_ar": ar, "days_in_ar": dar})
    return out
