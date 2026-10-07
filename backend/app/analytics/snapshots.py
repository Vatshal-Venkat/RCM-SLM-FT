"""Monthly KPI snapshots (persisted for audit and fast trend charts)."""

from __future__ import annotations

from datetime import date

from sqlalchemy import delete, func, select

from app.analytics.filters import AnalyticsFilters, dataset_as_of
from app.analytics.kpis import compute_kpis
from app.analytics.timeseries import month_ends
from app.db.session import get_sessionmaker
from app.models.rcm import Claim, KPISnapshot


def refresh_kpi_snapshots() -> int:
    with get_sessionmaker()() as db:
        first = db.scalar(select(func.min(Claim.claim_date)))
        if first is None:
            return 0
        as_of = dataset_as_of(db)
        db.execute(delete(KPISnapshot))
        n = 0
        for month, month_end in month_ends(first, as_of):
            start = date(month_end.year, month_end.month, 1)
            k = compute_kpis(db, AnalyticsFilters(start_date=start, end_date=month_end))
            db.add(KPISnapshot(
                period=month, period_start=start, period_end=month_end, total_claims=k.total_claims,
                total_billed=k.total_billed, total_paid=k.total_paid, denial_rate=k.denial_rate,
                clean_claim_rate=k.clean_claim_rate, first_pass_resolution_rate=k.first_pass_resolution_rate,
                net_collection_rate=k.net_collection_rate, days_in_ar=k.days_in_ar, outstanding_ar=k.outstanding_ar,
            ))
            n += 1
        db.commit()
        return n
