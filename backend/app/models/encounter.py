"""Patient-journey data model: one row per visit, carried from booking to a closed account.

An encounter walks the 15-step workflow (book -> register -> eligibility -> prior auth -> check-in ->
consultation -> documentation -> charge capture -> coding -> scrub -> clearinghouse -> adjudication
-> payment posting -> patient billing -> close). Step artefacts (eligibility response, transcript,
SOAP note, scrub report, clearinghouse acknowledgments, remittance) are stored as JSON documents
on the encounter; billable service lines and the audit trail have their own tables.

Billed lines are mirrored into the `claims` table (one Claim row per line) when the claim is
submitted, so pipeline claims appear in the Claims explorer and analytics alongside the history.
Patient names entered at booking are demo input; no other identifiers are stored.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.rcm import Base, Money


class Stage:
    BOOKED = "booked"
    REGISTERED = "registered"
    ELIGIBILITY_VERIFIED = "eligibility_verified"
    AUTHORIZATION_CHECKED = "authorization_checked"
    CHECKED_IN = "checked_in"
    IN_CONSULTATION = "in_consultation"
    DOCUMENTED = "documented"
    CHARGES_CAPTURED = "charges_captured"
    CODED = "coded"
    CLAIM_SCRUBBED = "claim_scrubbed"
    SUBMITTED = "submitted"
    ADJUDICATED = "adjudicated"
    PAYMENT_POSTED = "payment_posted"
    PATIENT_BILLED = "patient_billed"
    CLOSED = "closed"

    # (stage, workflow step 1-15, label) -- the slide-4 workflow, in order.
    ORDER: tuple[tuple[str, int, str], ...] = (
        (BOOKED, 1, "Patient books appointment"),
        (REGISTERED, 2, "Register patient and insurance"),
        (ELIGIBILITY_VERIFIED, 3, "Verify eligibility and benefits"),
        (AUTHORIZATION_CHECKED, 4, "Prior authorization check"),
        (CHECKED_IN, 5, "Check in, collect copay"),
        (IN_CONSULTATION, 6, "Doctor consultation (AI scribe listening)"),
        (DOCUMENTED, 7, "Clinical notes in the health record"),
        (CHARGES_CAPTURED, 8, "Charge capture on superbill"),
        (CODED, 9, "Medical coding: diagnosis + service"),
        (CLAIM_SCRUBBED, 10, "Build and scrub the claim"),
        (SUBMITTED, 11, "Submit via clearinghouse"),
        (ADJUDICATED, 12, "Payer reviews (adjudication)"),
        (PAYMENT_POSTED, 13, "Insurer pays, payment posted"),
        (PATIENT_BILLED, 14, "Bill patient balance"),
        (CLOSED, 15, "Follow up and close the account"),
    )

    @classmethod
    def step(cls, stage: str) -> int:
        return next(s for st, s, _ in cls.ORDER if st == stage)


class Attention:
    """Human decisions the autopilot cannot make; `None` means the pipeline can keep going."""

    ELIGIBILITY = "eligibility"  # front desk: fix member ID / coverage
    CONSULTATION = "consultation"  # doctor: hold the visit (transcript needed)
    SIGN_OFF = "sign_off"  # doctor: review and sign note + codes
    SCRUB = "scrub"  # coder: claim error the scrubber could not fix
    DENIAL = "denial"  # biller: approve the drafted appeal (or accept the denial)
    PATIENT_PAYMENT = "patient_payment"  # patient: pay the remaining balance


class Encounter(Base):
    __tablename__ = "encounters"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)  # ENC-000001
    seq: Mapped[int] = mapped_column(Integer, unique=True)

    # Booking / registration
    patient_name: Mapped[str] = mapped_column(String(80))
    patient_id: Mapped[str] = mapped_column(ForeignKey("patients_synthetic.id"))
    birth_year: Mapped[int] = mapped_column(Integer)
    sex: Mapped[str] = mapped_column(String(1))
    state: Mapped[str] = mapped_column(String(2))
    payer_id: Mapped[str] = mapped_column(ForeignKey("payers.id"), index=True)
    member_id: Mapped[str] = mapped_column(String(20))
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.id"), index=True)
    doctor_id: Mapped[str] = mapped_column(String(16))
    new_patient: Mapped[bool] = mapped_column(Boolean, default=False)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime)
    visit_reason: Mapped[str] = mapped_column(String(200))

    # Workflow state
    stage: Mapped[str] = mapped_column(String(32), index=True)
    attention: Mapped[str | None] = mapped_column(String(24))
    attention_detail: Mapped[str | None] = mapped_column(String(300))
    claim_status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|scrubbed|rejected|accepted|pended|adjudicated|none
    submission_count: Mapped[int] = mapped_column(Integer, default=0)
    signed: Mapped[bool] = mapped_column(Boolean, default=False)
    sim_day: Mapped[int] = mapped_column(Integer, default=0)  # simulated days elapsed since the visit

    # Step artefacts
    eligibility: Mapped[dict | None] = mapped_column(JSON)
    checkin: Mapped[dict | None] = mapped_column(JSON)
    transcript: Mapped[list | None] = mapped_column(JSON)  # [{speaker, text}]
    note: Mapped[dict | None] = mapped_column(JSON)  # SOAP note + evidence
    coding: Mapped[dict | None] = mapped_column(JSON)  # diagnoses, E/M rationale, not-coded findings
    scrub: Mapped[dict | None] = mapped_column(JSON)
    clearinghouse: Mapped[list | None] = mapped_column(JSON)  # one entry per submission
    adjudication: Mapped[dict | None] = mapped_column(JSON)
    remittance: Mapped[list | None] = mapped_column(JSON)  # one ERA per payment
    appeal: Mapped[dict | None] = mapped_column(JSON)
    billing: Mapped[dict | None] = mapped_column(JSON)  # patient statement

    # Money (encounter totals, recomputed from lines + payments)
    total_charge: Mapped[float] = mapped_column(Money(), default=0)
    payer_paid: Mapped[float] = mapped_column(Money(), default=0)
    patient_responsibility: Mapped[float] = mapped_column(Money(), default=0)
    patient_paid: Mapped[float] = mapped_column(Money(), default=0)
    adjustments: Mapped[float] = mapped_column(Money(), default=0)
    balance: Mapped[float] = mapped_column(Money(), default=0)

    human_actions: Mapped[int] = mapped_column(Integer, default=0)
    automated_steps: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    lines: Mapped[list[EncounterLine]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan", order_by="EncounterLine.line_no")
    events: Mapped[list[EncounterEvent]] = relationship(
        back_populates="encounter", cascade="all, delete-orphan", order_by="EncounterEvent.id")


class EncounterLine(Base):
    """One billable service (CPT/HCPCS) with its coverage decision and adjudication outcome."""

    __tablename__ = "encounter_lines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    encounter_id: Mapped[str] = mapped_column(ForeignKey("encounters.id"), index=True)
    line_no: Mapped[int] = mapped_column(Integer)
    code: Mapped[str] = mapped_column(String(8))
    code_system: Mapped[str] = mapped_column(String(8))  # CPT | HCPCS
    description: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(24))
    modifier: Mapped[str | None] = mapped_column(String(12))  # space-separated, e.g. "25" or "RT GA"
    units: Mapped[int] = mapped_column(Integer, default=1)
    dx_codes: Mapped[list] = mapped_column(JSON, default=list)
    charge: Mapped[float] = mapped_column(Money())
    source: Mapped[str] = mapped_column(String(12), default="ai")  # ai | manual | rule
    confidence: Mapped[float] = mapped_column(Float, default=0.9)
    evidence: Mapped[str | None] = mapped_column(Text)
    rationale: Mapped[str | None] = mapped_column(Text)

    # Coverage (decided before the claim goes out)
    coverage_status: Mapped[str] = mapped_column(String(24), default="covered")  # covered|prior_auth_required|not_covered|medical_necessity_risk
    coverage_reason: Mapped[str | None] = mapped_column(Text)
    auth_status: Mapped[str | None] = mapped_column(String(16))  # approved|denied|not_required
    auth_number: Mapped[str | None] = mapped_column(String(24))
    billing_decision: Mapped[str] = mapped_column(String(20), default="bill_insurance")  # bill_insurance|bill_with_abn|self_pay|do_not_perform
    est_payer: Mapped[float] = mapped_column(Money(), default=0)
    est_patient: Mapped[float] = mapped_column(Money(), default=0)

    # Adjudication / posting
    line_status: Mapped[str] = mapped_column(String(16), default="draft")  # draft|submitted|paid|denied|self_pay|not_performed
    allowed: Mapped[float] = mapped_column(Money(), default=0)
    payer_paid: Mapped[float] = mapped_column(Money(), default=0)
    patient_resp: Mapped[float] = mapped_column(Money(), default=0)
    adjustment: Mapped[float] = mapped_column(Money(), default=0)
    carc: Mapped[str | None] = mapped_column(String(12))  # denial group+reason, e.g. CO-50
    claim_id: Mapped[str | None] = mapped_column(String(16))  # mirrored Claim row

    encounter: Mapped[Encounter] = relationship(back_populates="lines")


class EncounterEvent(Base):
    """Audit trail: who (patient, AI, doctor, payer...) did what at each workflow step."""

    __tablename__ = "encounter_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    encounter_id: Mapped[str] = mapped_column(ForeignKey("encounters.id"), index=True)
    step: Mapped[int] = mapped_column(Integer)
    actor: Mapped[str] = mapped_column(String(16))  # patient|front_desk|ai|doctor|coder|clearinghouse|payer|system
    title: Mapped[str] = mapped_column(String(160))
    detail: Mapped[str | None] = mapped_column(Text)
    level: Mapped[str] = mapped_column(String(8), default="info")  # info|success|warning|error
    automated: Mapped[bool] = mapped_column(Boolean, default=True)
    sim_day: Mapped[int] = mapped_column(Integer, default=0)
    at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    encounter: Mapped[Encounter] = relationship(back_populates="events")
