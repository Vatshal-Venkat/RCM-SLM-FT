"""Deterministic RCM KPI calculations.

Definitions match knowledge/kpi_definitions.md ("Platform calculation") so that the numbers the
analytics engine produces and the definitions the assistant explains are the same thing.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, timedelta

from sqlalchemy import and_, case, func, select
from sqlalchemy.orm import Session

from app.analytics.filters import AnalyticsFilters, pct, resolve_period
from app.models.rcm import Claim, ClaimStatus, Denial, Payment

DAYS_IN_AR_WINDOW = 90

KPI_DEFINITIONS: dict[str, dict] = {
    "total_claims": {"label": "Total Claims", "unit": "count", "better": "neutral",
                     "formula": "Count of claims first submitted in the period"},
    "total_billed": {"label": "Total Billed", "unit": "usd", "better": "neutral",
                     "formula": "Sum of billed charges for claims in the period"},
    "total_paid": {"label": "Total Revenue (Collected)", "unit": "usd", "better": "up",
                   "formula": "Payer + patient payments received during the period (cash basis, by payment date)"},
    "total_denied_amount": {"label": "Total Denied Amount", "unit": "usd", "better": "down",
                            "formula": "Sum of denied amounts on claims in the period"},
    "denial_rate": {"label": "Denial Rate", "unit": "pct", "better": "down",
                    "formula": "Claims denied (fully or partially) on adjudication / adjudicated claims x 100"},
    "clean_claim_rate": {"label": "Clean Claim Rate", "unit": "pct", "better": "up",
                         "formula": "Claims accepted on first submission with no front-end rejection / submitted claims x 100"},
    "first_pass_resolution_rate": {"label": "First Pass Resolution", "unit": "pct", "better": "up",
                                   "formula": "Claims paid on first submission with no rejection or denial / adjudicated claims x 100"},
    "days_in_ar": {"label": "Days in AR", "unit": "days", "better": "down",
                   "formula": "Outstanding AR at period end / average daily billed charges over the trailing 90 days"},
    "net_collection_rate": {"label": "Collection Rate", "unit": "pct", "better": "up",
                            "formula": "Payments / (billed - contractual adjustments) for closed claims x 100"},
    "outstanding_ar": {"label": "Outstanding AR", "unit": "usd", "better": "down",
                       "formula": "Unpaid balance of all claims at period end (point in time)"},
    "ar_over_90_pct": {"label": "AR > 90 Days", "unit": "pct", "better": "down",
                       "formula": "AR on claims older than 90 days at period end / outstanding AR x 100"},
    "average_claim_value": {"label": "Average Claim Value", "unit": "usd", "better": "neutral",
                            "formula": "Total billed / number of claims"},
    "payment_rate": {"label": "Payment Rate", "unit": "pct", "better": "up",
                     "formula": "Amount collected to date on claims submitted in the period / their billed charges x 100"},
    "avg_days_to_adjudicate": {"label": "Avg Days to Adjudicate", "unit": "days", "better": "down",
                               "formula": "Average days from claim submission to payer adjudication"},
}


@dataclass
class KPIValues:
    total_claims: int
    total_billed: float
    total_paid: float
    payer_paid: float
    patient_paid: float
    total_denied_amount: float
    adjudicated_claims: int
    denied_claims: int
    denial_rate: float | None
    clean_claim_rate: float | None
    first_pass_resolution_rate: float | None
    days_in_ar: float | None
    net_collection_rate: float | None
    outstanding_ar: float
    ar_over_90_pct: float | None
    average_claim_value: float | None
    payment_rate: float | None
    avg_days_to_adjudicate: float | None

    def as_dict(self) -> dict:
        return asdict(self)


def _f(x) -> float:
    return round(float(x or 0), 2)


def ar_as_of(db: Session, as_of: date, f: AnalyticsFilters, submitted_before: date | None = None) -> float:
    """Outstanding AR at a point in time, reconstructed from transaction dates.

    AR(D) = billed (submitted <= D) - payments (paid <= D) - contractual adjustments (adjudicated <= D)
            - write-offs (written off <= D). Equals SUM(claims.balance) when D is the as-of date.
    `submitted_before` restricts to claims submitted before that date (for AR aging).
    """
    claim_conds = [Claim.claim_date <= as_of, *f.entity_conditions()]
    if submitted_before:
        claim_conds.append(Claim.claim_date < submitted_before)
    writeoff_date = case((Claim.status == ClaimStatus.DENIED, Claim.closed_date), else_=Claim.adjudication_date)
    billed, contractual, writeoff = db.execute(
        select(
            func.sum(Claim.billed_amount),
            func.sum(case((Claim.adjudication_date <= as_of, Claim.contractual_adjustment), else_=0)),
            func.sum(case((writeoff_date <= as_of, Claim.writeoff_amount), else_=0)),
        ).where(*claim_conds)
    ).one()
    paid = db.scalar(
        select(func.sum(Payment.amount)).join(Claim, Payment.claim_id == Claim.id)
        .where(Payment.payment_date <= as_of, *claim_conds)
    )
    return round(max(0.0, (billed or 0) - (paid or 0) - (contractual or 0) - (writeoff or 0)), 2)


def ar_over_90(db: Session, as_of: date, f: AnalyticsFilters) -> float:
    """AR at `as_of` on claims submitted more than 90 days earlier."""
    return ar_as_of(db, as_of, f, submitted_before=as_of - timedelta(days=90))


def days_in_ar(db: Session, as_of: date, f: AnalyticsFilters) -> tuple[float | None, float]:
    ar = ar_as_of(db, as_of, f)
    window_start = as_of - timedelta(days=DAYS_IN_AR_WINDOW - 1)
    billed_90 = db.scalar(
        select(func.sum(Claim.billed_amount))
        .where(Claim.claim_date >= window_start, Claim.claim_date <= as_of, *f.entity_conditions())
    )
    avg_daily = (billed_90 or 0) / DAYS_IN_AR_WINDOW
    return (round(ar / avg_daily, 1) if avg_daily else None), ar


def compute_kpis(db: Session, f: AnalyticsFilters) -> KPIValues:
    f = resolve_period(db, f)
    conds = f.conditions()
    adjudicated = Claim.status.in_(ClaimStatus.ADJUDICATED)
    closed = Claim.balance <= 0.005

    row = db.execute(
        select(
            func.count(Claim.id),
            func.sum(Claim.billed_amount),
            func.sum(Claim.paid_amount),
            func.sum(Claim.patient_paid_amount),
            func.sum(case((adjudicated, 1), else_=0)),
            func.sum(case((and_(adjudicated, Claim.was_denied), 1), else_=0)),
            func.sum(case((Claim.was_rejected.is_(False), 1), else_=0)),
            func.sum(case((and_(adjudicated, Claim.first_pass_paid), 1), else_=0)),
            func.sum(case((closed, Claim.paid_amount + Claim.patient_paid_amount), else_=0)),
            func.sum(case((closed, Claim.billed_amount - Claim.contractual_adjustment), else_=0)),
        ).where(*conds)
    ).one()
    (n, billed, cohort_payer_paid, cohort_patient_paid, n_adj, n_denied, n_clean, n_fpr,
     closed_paid, closed_collectible) = row

    # Cash received during the period (any claim matching the payer/provider/status filters).
    payer_paid, patient_paid = db.execute(
        select(func.sum(case((Payment.source == "payer", Payment.amount), else_=0)),
               func.sum(case((Payment.source == "patient", Payment.amount), else_=0)))
        .join(Claim, Payment.claim_id == Claim.id)
        .where(Payment.payment_date >= f.start_date, Payment.payment_date <= f.end_date, *f.entity_conditions())
    ).one()

    denied_amount = db.scalar(select(func.sum(Denial.denied_amount)).join(Claim, Denial.claim_id == Claim.id).where(*conds))

    # Average days to adjudicate (portable: compute in Python over adjudicated rows' date pairs).
    pairs = db.execute(select(Claim.claim_date, Claim.adjudication_date).where(*conds, Claim.adjudication_date.isnot(None))).all()
    avg_adj = round(sum((a - c).days for c, a in pairs) / len(pairs), 1) if pairs else None

    dar, ar = days_in_ar(db, f.end_date, f)
    ar90 = ar_over_90(db, f.end_date, f)
    cohort_collected = (cohort_payer_paid or 0) + (cohort_patient_paid or 0)
    return KPIValues(
        total_claims=n or 0,
        total_billed=_f(billed),
        total_paid=_f((payer_paid or 0) + (patient_paid or 0)),
        payer_paid=_f(payer_paid),
        patient_paid=_f(patient_paid),
        total_denied_amount=_f(denied_amount),
        adjudicated_claims=n_adj or 0,
        denied_claims=n_denied or 0,
        denial_rate=pct(n_denied, n_adj),
        clean_claim_rate=pct(n_clean, n),
        first_pass_resolution_rate=pct(n_fpr, n_adj),
        days_in_ar=dar,
        net_collection_rate=pct(closed_paid, closed_collectible),
        outstanding_ar=ar,
        ar_over_90_pct=pct(ar90, ar),
        average_claim_value=round(billed / n, 2) if n else None,
        payment_rate=pct(cohort_collected, billed),
        avg_days_to_adjudicate=avg_adj,
    )


def kpis_with_trend(db: Session, f: AnalyticsFilters) -> dict:
    """Current-period KPIs plus the previous equal-length period for trend indicators."""
    f = resolve_period(db, f)
    cur = compute_kpis(db, f)
    prev_f = f.previous_period()
    prev = compute_kpis(db, prev_f)
    cards = []
    for key, meta in KPI_DEFINITIONS.items():
        c, p = getattr(cur, key), getattr(prev, key)
        change = None
        if c is not None and p not in (None, 0):
            change = round(c - p, 2) if meta["unit"] in ("pct", "days") else round(100.0 * (c - p) / p, 1)
        cards.append({
            "key": key, **meta, "value": c, "previous": p, "change": change,
            "change_kind": "points" if meta["unit"] in ("pct", "days") else "percent",
        })
    return {
        "period": {"start": f.start_date.isoformat(), "end": f.end_date.isoformat()},
        "previous_period": {"start": prev_f.start_date.isoformat(), "end": prev_f.end_date.isoformat()},
        "kpis": cards,
        "values": cur.as_dict(),
        "previous_values": prev.as_dict(),
    }
