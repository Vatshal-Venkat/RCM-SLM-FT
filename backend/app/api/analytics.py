from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analytics import breakdowns, timeseries
from app.analytics.filters import AnalyticsFilters, dataset_as_of, resolve_period
from app.analytics.kpis import KPI_DEFINITIONS, kpis_with_trend
from app.api.params import analytics_filters
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.models.rcm import Claim, ClaimStatus, DatasetMetadata, Payer, Provider

router = APIRouter(tags=["analytics"], dependencies=[Depends(rate_limit("analytics", "rate_limit_default_per_minute"))])


@router.get("/api/kpis")
def kpis(f: AnalyticsFilters = Depends(analytics_filters), db: Session = Depends(get_db)) -> dict:
    """KPI cards for the period (default: trailing 90 days) with the previous period for trends."""
    return kpis_with_trend(db, f)


@router.get("/api/kpis/definitions")
def kpi_definitions() -> dict:
    return KPI_DEFINITIONS


@router.get("/api/analytics/overview")
def overview(f: AnalyticsFilters = Depends(analytics_filters), db: Session = Depends(get_db)) -> dict:
    """Everything the executive dashboard needs in one call."""
    k = kpis_with_trend(db, f)
    # Charts show a 12-month context ending at the KPI period end.
    chart_f = resolve_period(db, AnalyticsFilters(end_date=f.end_date, payer_ids=f.payer_ids,
                                                  provider_ids=f.provider_ids, statuses=f.statuses), default_days=365)
    if f.start_date and f.start_date < chart_f.start_date:
        chart_f = AnalyticsFilters(start_date=f.start_date, end_date=chart_f.end_date, payer_ids=f.payer_ids,
                                   provider_ids=f.provider_ids, statuses=f.statuses)
    return {
        **k,
        "claims_over_time": timeseries.claims_over_time(db, chart_f),
        "payments_over_time": timeseries.payments_over_time(db, chart_f),
        "ar_over_time": timeseries.ar_over_time(db, chart_f),
        "status_distribution": breakdowns.status_distribution(db, resolve_period(db, f)),
        "top_denial_reasons": breakdowns.denial_reasons(db, resolve_period(db, f), limit=6),
        "payers": breakdowns.payer_performance(db, resolve_period(db, f)),
    }


@router.get("/api/analytics/denials")
def denials(f: AnalyticsFilters = Depends(analytics_filters), db: Session = Depends(get_db)) -> dict:
    f = resolve_period(db, f, default_days=365)
    return {
        "period": {"start": f.start_date.isoformat(), "end": f.end_date.isoformat()},
        "reasons": breakdowns.denial_reasons(db, f),
        "categories": breakdowns.denial_categories(db, f),
        "over_time": timeseries.denials_over_time(db, f),
        "by_payer": [{k: p[k] for k in ("id", "name", "adjudicated", "denied", "denial_rate")}
                     for p in breakdowns.payer_performance(db, f)],
        "by_provider": [{k: p[k] for k in ("id", "name", "adjudicated", "denied", "denial_rate")}
                        for p in breakdowns.provider_performance(db, f)],
    }


@router.get("/api/analytics/payments")
def payments(f: AnalyticsFilters = Depends(analytics_filters), db: Session = Depends(get_db)) -> dict:
    f = resolve_period(db, f, default_days=365)
    return {
        "period": {"start": f.start_date.isoformat(), "end": f.end_date.isoformat()},
        "over_time": timeseries.payments_over_time(db, f),
        "ar_over_time": timeseries.ar_over_time(db, f),
    }


@router.get("/api/analytics/payers")
def payers(f: AnalyticsFilters = Depends(analytics_filters), db: Session = Depends(get_db)) -> dict:
    f = resolve_period(db, f, default_days=365)
    return {"period": {"start": f.start_date.isoformat(), "end": f.end_date.isoformat()},
            "payers": breakdowns.payer_performance(db, f)}


@router.get("/api/analytics/providers")
def providers(f: AnalyticsFilters = Depends(analytics_filters), db: Session = Depends(get_db)) -> dict:
    f = resolve_period(db, f, default_days=365)
    return {"period": {"start": f.start_date.isoformat(), "end": f.end_date.isoformat()},
            "providers": breakdowns.provider_performance(db, f)}


@router.get("/api/analytics/filters")
def filter_options(db: Session = Depends(get_db)) -> dict:
    """Options for dashboard filter controls."""
    lo, hi = db.execute(select(func.min(Claim.claim_date), func.max(Claim.claim_date))).one()
    meta = {m.key: m.value for m in db.scalars(select(DatasetMetadata))}
    return {
        "payers": [{"id": p.id, "name": p.name, "type": p.payer_type} for p in db.scalars(select(Payer).order_by(Payer.name))],
        "providers": [{"id": p.id, "name": p.name, "specialty": p.specialty}
                      for p in db.scalars(select(Provider).order_by(Provider.name))],
        "statuses": list(ClaimStatus.ALL),
        "date_range": {"min": lo.isoformat() if lo else None, "max": hi.isoformat() if hi else None},
        "as_of": dataset_as_of(db).isoformat(),
        "data_notice": meta.get("data_notice"),
    }
