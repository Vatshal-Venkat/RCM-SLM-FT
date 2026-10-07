from datetime import date

from sqlalchemy import func, select

from app.analytics import breakdowns, timeseries
from app.analytics.filters import AnalyticsFilters
from app.analytics.kpis import ar_as_of, compute_kpis, kpis_with_trend
from app.models.rcm import Claim, ClaimStatus
from tests.conftest import AS_OF


def test_synthetic_claims_balance(seeded_db):
    for c in seeded_db["claims"]:
        total = c["paid_amount"] + c["patient_paid_amount"] + c["contractual_adjustment"] + c["writeoff_amount"] + c["balance"]
        assert abs(c["billed_amount"] - total) < 0.02, c["id"]
        assert c["balance"] >= 0


def test_synthetic_data_has_no_direct_identifiers(seeded_db):
    assert set(seeded_db["patients_synthetic"][0]) == {"id", "birth_year", "sex", "state", "primary_payer_id"}


def test_ar_reconstruction_matches_balances_at_as_of(db):
    assert ar_as_of(db, AS_OF, AnalyticsFilters()) == round(db.scalar(select(func.sum(Claim.balance))), 2)


def test_ar_reconstruction_respects_entity_filters(db):
    f = AnalyticsFilters(payer_ids=("PYR-COB",))
    expected = db.scalar(select(func.sum(Claim.balance)).where(Claim.payer_id == "PYR-COB"))
    assert ar_as_of(db, AS_OF, f) == round(expected, 2)


def test_kpis_match_direct_sql(db):
    f = AnalyticsFilters(start_date=date(2026, 4, 1), end_date=date(2026, 6, 30))
    k = compute_kpis(db, f)
    period = [Claim.claim_date >= f.start_date, Claim.claim_date <= f.end_date]
    adj = db.scalar(select(func.count()).where(*period, Claim.status.in_(ClaimStatus.ADJUDICATED)))
    denied = db.scalar(select(func.count()).where(*period, Claim.status.in_(ClaimStatus.ADJUDICATED), Claim.was_denied))
    assert k.total_claims == db.scalar(select(func.count()).where(*period))
    assert k.adjudicated_claims == adj and k.denied_claims == denied
    assert k.denial_rate == round(100 * denied / adj, 1)
    assert 0 < k.first_pass_resolution_rate <= 100
    assert 0 < k.clean_claim_rate <= 100
    assert k.days_in_ar and k.days_in_ar > 0


def test_kpis_with_trend_has_previous_period(db):
    out = kpis_with_trend(db, AnalyticsFilters(start_date=date(2026, 7, 1), end_date=date(2026, 9, 30)))
    # Equal-length previous period: Jul 1 - Sep 30 is 92 days.
    assert out["previous_period"] == {"start": "2026-03-31", "end": "2026-06-30"}
    cards = {c["key"]: c for c in out["kpis"]}
    assert {"denial_rate", "days_in_ar", "clean_claim_rate", "outstanding_ar"} <= set(cards)
    assert cards["denial_rate"]["change_kind"] == "points"


def test_payer_breakdown_sums_to_total(db):
    f = AnalyticsFilters(start_date=date(2026, 2, 1), end_date=AS_OF)
    payers = breakdowns.payer_performance(db, f)
    assert sum(p["claims"] for p in payers) == compute_kpis(db, f).total_claims


def test_timeseries_months_are_ordered(db):
    series = timeseries.claims_over_time(db, AnalyticsFilters(start_date=date(2026, 2, 1), end_date=AS_OF))
    months = [r["month"] for r in series]
    assert months == sorted(months) and months[-1] == "2026-09"


def test_ar_over_time_ends_at_current_balance(db):
    series = timeseries.ar_over_time(db, AnalyticsFilters(start_date=date(2026, 6, 1), end_date=AS_OF))
    assert series[-1]["outstanding_ar"] == round(db.scalar(select(func.sum(Claim.balance))), 2)
