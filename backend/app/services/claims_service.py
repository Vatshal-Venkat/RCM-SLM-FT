"""Claim listing and detail queries (database layer only, no AI)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.analytics.filters import AnalyticsFilters, dataset_as_of
from app.models.rcm import Claim, ClaimStatus, Denial, PatientSynthetic

SORTABLE = {
    "claim_date": Claim.claim_date,
    "service_date": Claim.service_date,
    "billed_amount": Claim.billed_amount,
    "paid_amount": Claim.paid_amount,
    "balance": Claim.balance,
    "status": Claim.status,
}


@dataclass(frozen=True)
class ClaimQuery:
    filters: AnalyticsFilters
    search: str | None = None
    denial_category: str | None = None
    open_only: bool = False
    sort: str = "claim_date"
    descending: bool = True
    page: int = 1
    page_size: int = 25


def claim_days_in_ar(c: Claim, as_of: date) -> int:
    """Days from first submission until closed (or until the as-of date if still open)."""
    end = c.closed_date if (c.closed_date and c.balance <= 0.005) else as_of
    return max(0, (end - c.claim_date).days)


def list_claims(db: Session, q: ClaimQuery) -> tuple[list[Claim], int, date]:
    conds = q.filters.conditions()
    if q.search:
        s = f"%{q.search.strip().upper()}%"
        conds.append(or_(Claim.id.ilike(s), Claim.cpt_code.ilike(s), Claim.icd10_code.ilike(s),
                         Claim.denial_reason_code.ilike(q.search.strip())))
    if q.denial_category:
        conds.append(Claim.denial_category == q.denial_category)
    if q.open_only:
        conds.append(Claim.balance > 0.005)

    total = db.scalar(select(func.count(Claim.id)).where(*conds)) or 0
    col = SORTABLE.get(q.sort, Claim.claim_date)
    stmt = (
        select(Claim).options(selectinload(Claim.payer), selectinload(Claim.provider))
        .where(*conds).order_by(col.desc() if q.descending else col.asc(), Claim.id.desc())
        .offset((q.page - 1) * q.page_size).limit(q.page_size)
    )
    return list(db.scalars(stmt)), total, dataset_as_of(db)


def get_claim(db: Session, claim_id: str) -> tuple[Claim | None, PatientSynthetic | None, date]:
    claim = db.scalar(
        select(Claim).where(Claim.id == claim_id.upper())
        .options(selectinload(Claim.payer), selectinload(Claim.provider), selectinload(Claim.payments),
                 selectinload(Claim.denials), selectinload(Claim.history))
    )
    patient = db.get(PatientSynthetic, claim.patient_id) if claim else None
    return claim, patient, dataset_as_of(db)


def priority_score(c: Claim, as_of: date, timely_filing_days: int) -> tuple[float, list[str]]:
    """Deterministic follow-up priority for an open claim (higher = work first), with reasons."""
    reasons: list[str] = []
    age = (as_of - c.claim_date).days
    score = min(c.balance / 500.0, 10.0)  # dollar value, capped
    if c.balance >= 1000:
        reasons.append(f"high balance (${c.balance:,.0f})")
    if c.status in (ClaimStatus.DENIED, ClaimStatus.REJECTED):
        score += 4
        reasons.append(f"unresolved {c.status} claim")
    if c.status == ClaimStatus.DENIED and c.denial_category in {"missing_information", "coding", "documentation",
                                                                 "authorization", "coordination_of_benefits"}:
        score += 2
        reasons.append(f"recoverable denial ({c.denial_category.replace('_', ' ')})")
    days_left = timely_filing_days - (as_of - c.service_date).days
    if c.status in (ClaimStatus.REJECTED,) and days_left < 45:
        score += 5
        reasons.append(f"{days_left} days left before timely filing limit")
    if c.status == ClaimStatus.DENIED and c.history:
        denied_on = max((h.status_date for h in c.history if h.status == "denied"), default=None)
        if denied_on and (as_of - denied_on).days > 45:
            score += 2
            reasons.append("denial aging past 45 days (appeal deadline risk)")
    if c.status == ClaimStatus.PENDING and age > 45:
        score += 3
        reasons.append(f"no payer response after {age} days")
    if age > 90:
        score += 2
        reasons.append("aged over 90 days")
    return round(score, 2), reasons


def prioritized_open_claims(db: Session, f: AnalyticsFilters, limit: int = 10) -> list[dict]:
    as_of = dataset_as_of(db)
    stmt = (
        select(Claim).options(selectinload(Claim.payer), selectinload(Claim.history))
        .where(*f.entity_conditions(), Claim.balance > 0.005,
               Claim.status.in_((ClaimStatus.DENIED, ClaimStatus.REJECTED, ClaimStatus.PENDING, ClaimStatus.APPEALED)))
    )
    scored = []
    for c in db.scalars(stmt):
        s, reasons = priority_score(c, as_of, c.payer.timely_filing_days)
        scored.append({"claim_id": c.id, "payer": c.payer.name, "status": c.status, "balance": c.balance,
                       "age_days": (as_of - c.claim_date).days, "denial_reason_code": c.denial_reason_code,
                       "score": s, "reasons": reasons})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[:limit]


def denial_category_counts(db: Session) -> dict[str, int]:
    rows = db.execute(select(Denial.category, func.count(Denial.id)).group_by(Denial.category)).all()
    return {r[0]: r[1] for r in rows}
