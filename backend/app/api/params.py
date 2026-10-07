"""Query-parameter parsing shared by analytics and claims routes."""

from __future__ import annotations

import re
from datetime import date

from fastapi import HTTPException, Query, status

from app.analytics.filters import AnalyticsFilters
from app.models.rcm import ClaimStatus

_ID_RE = re.compile(r"^[A-Za-z0-9-]{1,16}$")


def analytics_filters(
    start_date: date | None = Query(None, description="Claim submission date from (inclusive)"),
    end_date: date | None = Query(None, description="Claim submission date to (inclusive)"),
    payer_id: list[str] = Query(default_factory=list, max_length=20),
    provider_id: list[str] = Query(default_factory=list, max_length=50),
    claim_status: list[str] = Query(default_factory=list, alias="status"),
) -> AnalyticsFilters:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "start_date must be on or before end_date")
    if any(not _ID_RE.match(i) for i in [*payer_id, *provider_id]):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Invalid payer_id or provider_id")
    bad = [s for s in claim_status if s not in ClaimStatus.ALL]
    if bad:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, f"Unknown status: {', '.join(bad)}")
    return AnalyticsFilters(
        start_date=start_date, end_date=end_date, payer_ids=tuple(payer_id),
        provider_ids=tuple(provider_id), statuses=tuple(claim_status),
    )
