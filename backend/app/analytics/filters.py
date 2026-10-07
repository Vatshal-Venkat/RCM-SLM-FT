"""Shared analytics filters and SQL helpers."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, timedelta

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session

from app.models.rcm import Claim, DatasetMetadata

DEFAULT_WINDOW_DAYS = 90


@dataclass(frozen=True)
class AnalyticsFilters:
    """Claim-level filters. Dates filter on `claim_date` (first submission date)."""

    start_date: date | None = None
    end_date: date | None = None
    payer_ids: tuple[str, ...] = field(default_factory=tuple)
    provider_ids: tuple[str, ...] = field(default_factory=tuple)
    statuses: tuple[str, ...] = field(default_factory=tuple)

    def entity_conditions(self) -> list[ColumnElement[bool]]:
        """Payer/provider/status conditions (no dates): used for point-in-time AR."""
        conds: list[ColumnElement[bool]] = []
        if self.payer_ids:
            conds.append(Claim.payer_id.in_(self.payer_ids))
        if self.provider_ids:
            conds.append(Claim.provider_id.in_(self.provider_ids))
        if self.statuses:
            conds.append(Claim.status.in_(self.statuses))
        return conds

    def conditions(self) -> list[ColumnElement[bool]]:
        conds = self.entity_conditions()
        if self.start_date:
            conds.append(Claim.claim_date >= self.start_date)
        if self.end_date:
            conds.append(Claim.claim_date <= self.end_date)
        return conds

    def previous_period(self) -> AnalyticsFilters:
        """The equal-length period immediately before this one (for trend indicators)."""
        assert self.start_date and self.end_date
        length = (self.end_date - self.start_date).days + 1
        return replace(self, start_date=self.start_date - timedelta(days=length),
                       end_date=self.start_date - timedelta(days=1))


def dataset_as_of(db: Session) -> date:
    """The dataset's as-of date (synthetic data is generated up to a fixed date)."""
    row = db.get(DatasetMetadata, "as_of_date")
    if row:
        return date.fromisoformat(row.value)
    latest = db.scalar(select(func.max(Claim.claim_date)))
    return latest or date.today()


def resolve_period(db: Session, f: AnalyticsFilters, default_days: int = DEFAULT_WINDOW_DAYS) -> AnalyticsFilters:
    """Fill in missing dates: end defaults to the dataset as-of date, start to `default_days` before end."""
    end = f.end_date or dataset_as_of(db)
    start = f.start_date or (end - timedelta(days=default_days - 1))
    return replace(f, start_date=start, end_date=end)


def month_bucket(db: Session, col) -> ColumnElement[str]:
    """'YYYY-MM' bucket expression for the active SQL dialect."""
    if db.get_bind().dialect.name == "sqlite":
        return func.strftime("%Y-%m", col)
    return func.to_char(col, "YYYY-MM")


def pct(numerator: float | None, denominator: float | None, digits: int = 1) -> float | None:
    if not denominator:
        return None
    return round(100.0 * (numerator or 0) / denominator, digits)
