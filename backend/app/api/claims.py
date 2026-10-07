from __future__ import annotations

from datetime import date
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from app.ai.llm_provider import LLMProviderError
from app.analytics.filters import AnalyticsFilters
from app.api.deps import ensure_llm_ready, get_claim_analysis_service
from app.api.params import analytics_filters
from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.models.rcm import Claim, PatientSynthetic
from app.schemas.claims import (
    ClaimDetail,
    ClaimListResponse,
    ClaimSummary,
    DenialOut,
    PatientOut,
    PaymentOut,
    StatusEventOut,
)
from app.services.claim_analysis import ClaimAnalysisService
from app.services.claims_service import SORTABLE, ClaimQuery, claim_days_in_ar, get_claim, list_claims

router = APIRouter(prefix="/api/claims", tags=["claims"],
                   dependencies=[Depends(rate_limit("claims", "rate_limit_default_per_minute"))])

CLAIM_ID = Path(..., pattern=r"^[A-Za-z]{3}-\d{4,10}$", description="Claim ID, e.g. CLM-000123")


@router.get("", response_model=ClaimListResponse)
def claims(
    f: AnalyticsFilters = Depends(analytics_filters),
    search: str | None = Query(None, max_length=40, pattern=r"^[A-Za-z0-9.\- ]*$"),
    denial_category: str | None = Query(None, max_length=32, pattern=r"^[a-z_]*$"),
    open_only: bool = False,
    sort: Literal[tuple(SORTABLE)] = "claim_date",  # type: ignore[valid-type]
    order: Literal["asc", "desc"] = "desc",
    page: int = Query(1, ge=1, le=10_000),
    page_size: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
) -> ClaimListResponse:
    rows, total, as_of = list_claims(db, ClaimQuery(
        filters=f, search=search or None, denial_category=denial_category, open_only=open_only,
        sort=sort, descending=order == "desc", page=page, page_size=page_size,
    ))
    return ClaimListResponse(
        items=[_summary(c, as_of) for c in rows], total=total, page=page, page_size=page_size, as_of=as_of,
    )


@router.get("/{claim_id}", response_model=ClaimDetail)
def claim_detail(claim_id: str = CLAIM_ID, db: Session = Depends(get_db)) -> ClaimDetail:
    claim, patient, as_of = get_claim(db, claim_id)
    if claim is None or patient is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    return build_claim_detail(claim, patient, as_of)


@router.post("/{claim_id}/analyze", dependencies=[Depends(rate_limit("chat", "rate_limit_chat_per_minute"))])
def analyze_claim(
    claim_id: str = CLAIM_ID,
    db: Session = Depends(get_db),
    service: ClaimAnalysisService = Depends(get_claim_analysis_service),
) -> dict:
    """Rule-based findings + grounded SLM explanation for one claim."""
    ensure_llm_ready()
    try:
        result = service.analyze(db, claim_id)
    except LLMProviderError as e:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(e)) from e
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Claim not found")
    return result


def _summary(c: Claim, as_of: date) -> ClaimSummary:
    return ClaimSummary(
        claim_id=c.id, patient_id=c.patient_id, provider_id=c.provider_id, provider=c.provider.name,
        payer_id=c.payer_id, payer=c.payer.name, claim_date=c.claim_date, service_date=c.service_date,
        cpt_code=c.cpt_code, billed_amount=c.billed_amount, allowed_amount=c.allowed_amount,
        paid_amount=round(c.paid_amount + c.patient_paid_amount, 2), balance=c.balance, status=c.status,
        denial_reason_code=c.denial_reason_code, denial_category=c.denial_category,
        days_in_ar=claim_days_in_ar(c, as_of),
    )


def _age_band(birth_year: int, as_of: date) -> str:
    age = as_of.year - birth_year
    if age < 18:
        return "0-17"
    lo = min(80, (age // 10) * 10)
    return "80+" if lo >= 80 else f"{lo}-{lo + 9}"


def build_claim_detail(c: Claim, p: PatientSynthetic, as_of: date) -> ClaimDetail:
    tf = c.payer.timely_filing_days
    return ClaimDetail(
        claim_id=c.id,
        patient=PatientOut(patient_id=p.id, age_band=_age_band(p.birth_year, as_of), sex=p.sex, state=p.state),
        provider_id=c.provider_id, provider=c.provider.name, provider_specialty=c.provider.specialty,
        payer_id=c.payer_id, payer=c.payer.name, payer_type=c.payer.payer_type, claim_type=c.claim_type,
        claim_date=c.claim_date, service_date=c.service_date, adjudication_date=c.adjudication_date,
        closed_date=c.closed_date, cpt_code=c.cpt_code, cpt_description=c.cpt_description, modifier=c.modifier,
        units=c.units, icd10_code=c.icd10_code, icd10_description=c.icd10_description,
        place_of_service=c.place_of_service, requires_authorization=c.requires_authorization,
        authorization_number=c.authorization_number, billed_amount=c.billed_amount,
        allowed_amount=c.allowed_amount, paid_amount=c.paid_amount, patient_responsibility=c.patient_responsibility,
        patient_paid_amount=c.patient_paid_amount, contractual_adjustment=c.contractual_adjustment,
        writeoff_amount=c.writeoff_amount, adjustment_total=round(c.contractual_adjustment + c.writeoff_amount, 2),
        balance=c.balance, status=c.status, denial_reason_code=c.denial_reason_code, denial_reason=c.denial_reason,
        denial_category=c.denial_category, rejection_reason=c.rejection_reason, submission_count=c.submission_count,
        was_rejected=c.was_rejected, was_denied=c.was_denied, first_pass_paid=c.first_pass_paid,
        days_in_ar=claim_days_in_ar(c, as_of), timely_filing_days=tf,
        days_until_timely_filing=tf - (as_of - c.service_date).days,
        payments=[PaymentOut(source=x.source, amount=x.amount, payment_date=x.payment_date, method=x.method,
                             trace_number=x.trace_number) for x in sorted(c.payments, key=lambda x: x.payment_date)],
        denials=[DenialOut(carc_code=d.carc_code, group_code=d.group_code, rarc_code=d.rarc_code,
                           description=d.description, category=d.category, denied_amount=d.denied_amount,
                           denial_date=d.denial_date, preventable=d.preventable, appeal_status=d.appeal_status,
                           appeal_date=d.appeal_date, resolution_date=d.resolution_date) for d in c.denials],
        history=[StatusEventOut(status=h.status, status_date=h.status_date, note=h.note) for h in c.history],
        as_of=as_of,
    )
