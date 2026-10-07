"""Categorical breakdowns: denial reasons, payers, providers, claim status."""

from __future__ import annotations

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.analytics.filters import AnalyticsFilters, pct, resolve_period
from app.models.rcm import Claim, ClaimStatus, Denial, Payer, Provider


def denial_reasons(db: Session, f: AnalyticsFilters, limit: int = 15) -> list[dict]:
    f = resolve_period(db, f, default_days=365)
    rows = db.execute(
        select(
            Denial.carc_code, Denial.group_code, Denial.description, Denial.category,
            func.count(Denial.id), func.sum(Denial.denied_amount),
            func.sum(case((Denial.preventable, 1), else_=0)),
            func.sum(case((Denial.appeal_status == "overturned", 1), else_=0)),
            func.sum(case((Denial.appeal_status.in_(("overturned", "upheld")), 1), else_=0)),
        ).join(Claim, Denial.claim_id == Claim.id).where(*f.conditions())
        .group_by(Denial.carc_code, Denial.group_code, Denial.description, Denial.category)
        .order_by(func.count(Denial.id).desc()).limit(limit)
    ).all()
    total = sum(r[4] for r in rows) or 1
    return [
        {"carc_code": r[0], "group_code": r[1], "description": r[2], "category": r[3], "count": r[4],
         "denied_amount": round(r[5] or 0, 2), "share_pct": round(100.0 * r[4] / total, 1),
         "preventable": bool(r[6]), "appeals_decided": r[8], "overturn_rate": pct(r[7], r[8])}
        for r in rows
    ]


def denial_categories(db: Session, f: AnalyticsFilters) -> list[dict]:
    f = resolve_period(db, f, default_days=365)
    rows = db.execute(
        select(Denial.category, func.count(Denial.id), func.sum(Denial.denied_amount))
        .join(Claim, Denial.claim_id == Claim.id).where(*f.conditions())
        .group_by(Denial.category).order_by(func.count(Denial.id).desc())
    ).all()
    total = sum(r[1] for r in rows) or 1
    return [{"category": r[0], "count": r[1], "denied_amount": round(r[2] or 0, 2),
             "share_pct": round(100.0 * r[1] / total, 1)} for r in rows]


def _entity_performance(db: Session, f: AnalyticsFilters, key_col, name_col, join_model, join_on) -> list[dict]:
    f = resolve_period(db, f, default_days=365)
    adjudicated = Claim.status.in_(ClaimStatus.ADJUDICATED)
    rows = db.execute(
        select(
            key_col, name_col,
            func.count(Claim.id),
            func.sum(Claim.billed_amount),
            func.sum(Claim.paid_amount + Claim.patient_paid_amount),
            func.sum(case((adjudicated, 1), else_=0)),
            func.sum(case((and_(adjudicated, Claim.was_denied), 1), else_=0)),
            func.sum(case((Claim.was_rejected, 1), else_=0)),
            func.sum(case((and_(adjudicated, Claim.first_pass_paid), 1), else_=0)),
            func.sum(Claim.balance),
            func.sum(case((Claim.status == ClaimStatus.PENDING, 1), else_=0)),
        ).join(join_model, join_on).where(*f.conditions())
        .group_by(key_col, name_col)
    ).all()
    # Days to adjudicate per entity, computed portably in Python.
    pairs = db.execute(
        select(key_col, Claim.claim_date, Claim.adjudication_date)
        .join(join_model, join_on).where(*f.conditions(), Claim.adjudication_date.isnot(None))
    ).all()
    days: dict[str, list[int]] = {}
    for k, c, a in pairs:
        days.setdefault(k, []).append((a - c).days)

    out = []
    for r in rows:
        d = days.get(r[0], [])
        out.append({
            "id": r[0], "name": r[1], "claims": r[2], "billed": round(r[3] or 0, 2), "collected": round(r[4] or 0, 2),
            "adjudicated": r[5], "denied": r[6], "denial_rate": pct(r[6], r[5]),
            "clean_claim_rate": pct(r[2] - r[7], r[2]), "first_pass_resolution_rate": pct(r[8], r[5]),
            "outstanding_ar": round(r[9] or 0, 2), "pending_claims": r[10], "payment_rate": pct(r[4], r[3]),
            "avg_days_to_adjudicate": round(sum(d) / len(d), 1) if d else None,
        })
    return sorted(out, key=lambda x: x["billed"], reverse=True)


def payer_performance(db: Session, f: AnalyticsFilters) -> list[dict]:
    return _entity_performance(db, f, Payer.id, Payer.name, Payer, Claim.payer_id == Payer.id)


def provider_performance(db: Session, f: AnalyticsFilters) -> list[dict]:
    return _entity_performance(db, f, Provider.id, Provider.name, Provider, Claim.provider_id == Provider.id)


def status_distribution(db: Session, f: AnalyticsFilters) -> list[dict]:
    f = resolve_period(db, f, default_days=365)
    rows = db.execute(
        select(Claim.status, func.count(Claim.id), func.sum(Claim.billed_amount), func.sum(Claim.balance))
        .where(*f.conditions()).group_by(Claim.status).order_by(func.count(Claim.id).desc())
    ).all()
    total = sum(r[1] for r in rows) or 1
    return [{"status": r[0], "count": r[1], "billed": round(r[2] or 0, 2), "balance": round(r[3] or 0, 2),
             "share_pct": round(100.0 * r[1] / total, 1)} for r in rows]
