from __future__ import annotations

from datetime import date

from pydantic import BaseModel


class ClaimSummary(BaseModel):
    claim_id: str
    patient_id: str
    provider_id: str
    provider: str
    payer_id: str
    payer: str
    claim_date: date
    service_date: date
    cpt_code: str
    billed_amount: float
    allowed_amount: float
    paid_amount: float
    balance: float
    status: str
    denial_reason_code: str | None
    denial_category: str | None
    days_in_ar: int


class ClaimListResponse(BaseModel):
    items: list[ClaimSummary]
    total: int
    page: int
    page_size: int
    as_of: date


class PaymentOut(BaseModel):
    source: str
    amount: float
    payment_date: date
    method: str
    trace_number: str | None


class DenialOut(BaseModel):
    carc_code: str
    group_code: str
    rarc_code: str | None
    description: str
    category: str
    denied_amount: float
    denial_date: date
    preventable: bool
    appeal_status: str
    appeal_date: date | None
    resolution_date: date | None


class StatusEventOut(BaseModel):
    status: str
    status_date: date
    note: str | None


class PatientOut(BaseModel):
    patient_id: str
    age_band: str
    sex: str
    state: str
    synthetic: bool = True


class ClaimDetail(BaseModel):
    claim_id: str
    patient: PatientOut
    provider_id: str
    provider: str
    provider_specialty: str
    payer_id: str
    payer: str
    payer_type: str
    claim_type: str
    claim_date: date
    service_date: date
    adjudication_date: date | None
    closed_date: date | None
    cpt_code: str
    cpt_description: str
    modifier: str | None
    units: int
    icd10_code: str
    icd10_description: str
    place_of_service: str
    requires_authorization: bool
    authorization_number: str | None
    billed_amount: float
    allowed_amount: float
    paid_amount: float
    patient_responsibility: float
    patient_paid_amount: float
    contractual_adjustment: float
    writeoff_amount: float
    adjustment_total: float
    balance: float
    status: str
    denial_reason_code: str | None
    denial_reason: str | None
    denial_category: str | None
    rejection_reason: str | None
    submission_count: int
    was_rejected: bool
    was_denied: bool
    first_pass_paid: bool
    days_in_ar: int
    timely_filing_days: int
    days_until_timely_filing: int
    payments: list[PaymentOut]
    denials: list[DenialOut]
    history: list[StatusEventOut]
    as_of: date
