"""Patient-journey API: book a visit, record the consultation, and drive it to a closed account."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.rate_limit import rate_limit
from app.db.session import get_db
from app.models.encounter import Encounter, Stage
from app.pipeline import catalog as cat
from app.pipeline import engine
from app.pipeline.engine import PipelineError

router = APIRouter(prefix="/api/encounters", tags=["patient journey"],
                   dependencies=[Depends(rate_limit("encounters", "rate_limit_default_per_minute"))])

ENC_ID = Path(..., pattern=r"^ENC-\d{6}$", description="Encounter ID, e.g. ENC-000001")
SLOT_TIMES = [time(h, m) for h in range(9, 17) for m in (0, 30) if not (h == 12)]


# --------------------------------------------------------------------------- input models


class BookingIn(BaseModel):
    patient_name: str = Field(..., min_length=2, max_length=80, pattern=r"^[A-Za-z][A-Za-z .'\-]*$")
    birth_year: int = Field(..., ge=1900, le=2100)
    sex: Literal["F", "M"]
    state: str = Field(..., pattern=r"^[A-Za-z]{2}$")
    payer_id: str = Field(..., pattern=r"^PYR-[A-Z]{3}$")
    member_id: str = Field(..., min_length=1, max_length=20, pattern=r"^[A-Za-z0-9]+$")
    doctor_id: str = Field(..., pattern=r"^DR-\d{2}$")
    scheduled_at: datetime
    visit_reason: str = Field(..., min_length=2, max_length=200)
    new_patient: bool = False

    @field_validator("birth_year")
    @classmethod
    def _not_future(cls, v: int) -> int:
        if v > date.today().year:
            raise ValueError("birth year is in the future")
        return v


class RegistrationIn(BaseModel):
    member_id: str = Field(..., min_length=1, max_length=20, pattern=r"^[A-Za-z0-9]+$")
    payer_id: str | None = Field(None, pattern=r"^PYR-[A-Z]{3}$")


class UtteranceIn(BaseModel):
    speaker: Literal["doctor", "patient", "unknown"]
    text: str = Field(..., max_length=2000)


class TranscriptIn(BaseModel):
    utterances: list[UtteranceIn] = Field(..., max_length=400)


class LineIn(BaseModel):
    code: str = Field(..., pattern=r"^[A-Z0-9]{5}$")
    modifier: str | None = Field(None, pattern=r"^([0-9A-Z]{2}( [0-9A-Z]{2}){0,3})?$")
    units: int = Field(1, ge=1, le=99)
    billing_decision: Literal["bill_insurance", "bill_with_abn", "self_pay", "do_not_perform"] | None = None


class CodingIn(BaseModel):
    diagnoses: list[str] = Field(..., min_length=1, max_length=12)
    lines: list[LineIn] = Field(..., min_length=1, max_length=30)

    @field_validator("diagnoses")
    @classmethod
    def _dx_format(cls, v: list[str]) -> list[str]:
        import re
        for c in v:
            if not re.match(r"^[A-Z]\d{2}(\.[0-9A-Z]{1,4})?$", c):
                raise ValueError(f"invalid ICD-10-CM code {c!r}")
        return v


class DenialIn(BaseModel):
    action: Literal["appeal", "accept"]


class PaymentIn(BaseModel):
    amount: float | None = Field(None, gt=0, le=100_000)


# --------------------------------------------------------------------------- reference data


@router.get("/options")
def options() -> dict:
    """Doctors, insurance plans and sample conversations for the booking and scribe screens."""
    return {
        "doctors": [{"id": d.id, "name": d.name, "specialty": d.specialty, "provider_id": d.provider_id,
                     "provider": cat.PROVIDER_INFO[d.provider_id]["name"], "primary_care": d.primary_care} for d in cat.DOCTORS],
        "plans": [{"payer_id": p.payer_id, "payer": cat.PAYER_INFO[p.payer_id]["name"],
                   "payer_type": cat.PAYER_INFO[p.payer_id]["payer_type"], "plan_name": p.plan_name,
                   "member_id_example": p.member_id_example, "copay_pcp": p.copay_pcp, "copay_specialist": p.copay_specialist,
                   "deductible": p.deductible, "coinsurance_pct": round(p.coinsurance * 100)} for p in cat.PLANS.values()],
        "samples": [{k: v for k, v in s.items() if k != "transcript"}
                    | {"transcript": [{"speaker": a, "text": b} for a, b in s["transcript"]]} for s in cat.SAMPLES],
        "stages": [{"stage": s, "step": n, "label": label} for s, n, label in Stage.ORDER],
    }


@router.get("/slots")
def slots(doctor_id: str = Query(..., pattern=r"^DR-\d{2}$"), day: date = Query(...),
          db: Session = Depends(get_db)) -> dict:
    if doctor_id not in cat.DOCTOR_BY_ID:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown doctor")
    start = datetime.combine(day, time(0))
    taken = set(db.scalars(select(Encounter.scheduled_at).where(
        Encounter.doctor_id == doctor_id, Encounter.scheduled_at >= start, Encounter.scheduled_at < start + timedelta(days=1))))
    now = datetime.now()
    out = [{"time": t.strftime("%H:%M"), "available": datetime.combine(day, t) not in taken and datetime.combine(day, t) > now - timedelta(hours=12)}
           for t in SLOT_TIMES]
    return {"doctor_id": doctor_id, "day": day.isoformat(), "slots": out, "weekend": day.weekday() >= 5}


@router.get("/codes")
def code_search(q: str = Query("", max_length=40, pattern=r"^[A-Za-z0-9 .\-]*$")) -> dict:
    """Code lookup for the physician/coder edit screen (only codes the pipeline understands)."""
    ql = q.lower().strip()
    services = [{"code": c, "system": "HCPCS" if c[0].isalpha() else "CPT", "description": d, "charge": ch, "category": "em"}
                for c, (d, ch) in cat.EM_CODES.items()]
    services += [{"code": s.code, "system": s.system, "description": s.description, "charge": s.charge, "category": s.category}
                 for s in cat.SERVICES]
    dx = [{"code": c, "description": d} for c, d in engine.dx_lookup().items()]
    match = (lambda x: not ql or ql in x["code"].lower() or ql in x["description"].lower())
    return {"services": [s for s in services if match(s)][:40], "diagnoses": [d for d in dx if match(d)][:40]}


# --------------------------------------------------------------------------- encounters


@router.get("")
def list_encounters(db: Session = Depends(get_db)) -> dict:
    encs = list(db.scalars(select(Encounter).order_by(Encounter.scheduled_at.desc())))
    return {"items": [summary(e) for e in encs], "scorecard": engine.scorecard(encs)}


@router.post("", status_code=status.HTTP_201_CREATED)
def book(body: BookingIn, db: Session = Depends(get_db)) -> dict:
    try:
        enc = engine.book(db, **body.model_dump())
    except PipelineError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return detail(enc)


@router.get("/{encounter_id}")
def get_one(encounter_id: str = ENC_ID, db: Session = Depends(get_db)) -> dict:
    return detail(_load(db, encounter_id))


@router.post("/{encounter_id}/registration")
def registration(body: RegistrationIn, encounter_id: str = ENC_ID, db: Session = Depends(get_db)) -> dict:
    return _run(db, encounter_id, lambda e: engine.update_registration(db, e, body.member_id, body.payer_id))


@router.post("/{encounter_id}/advance")
def advance(encounter_id: str = ENC_ID, db: Session = Depends(get_db)) -> dict:
    enc = _load(db, encounter_id)
    r = engine.advance(db, enc)
    return detail(enc) | {"result": {"advanced": r.advanced, "message": r.message}}


@router.post("/{encounter_id}/autopilot")
def autopilot(encounter_id: str = ENC_ID, db: Session = Depends(get_db)) -> dict:
    enc = _load(db, encounter_id)
    done = engine.autopilot(db, enc)
    return detail(enc) | {"result": {"steps": done, "stopped_for": enc.attention, "message": enc.attention_detail}}


@router.post("/{encounter_id}/transcript")
def transcript(body: TranscriptIn, encounter_id: str = ENC_ID, db: Session = Depends(get_db)) -> dict:
    return _run(db, encounter_id, lambda e: engine.save_transcript(db, e, [u.model_dump() for u in body.utterances]))


@router.post("/{encounter_id}/scribe")
def run_scribe(encounter_id: str = ENC_ID, db: Session = Depends(get_db)) -> dict:
    def go(e: Encounter) -> Encounter:
        if e.attention == "consultation":
            e.attention = None
        return engine.run_scribe(db, e)
    return _run(db, encounter_id, go)


@router.post("/{encounter_id}/coding")
def coding(body: CodingIn, encounter_id: str = ENC_ID, db: Session = Depends(get_db)) -> dict:
    return _run(db, encounter_id, lambda e: engine.edit_coding(db, e, body.diagnoses, [ln.model_dump() for ln in body.lines]))


@router.post("/{encounter_id}/sign")
def sign(encounter_id: str = ENC_ID, db: Session = Depends(get_db)) -> dict:
    return _run(db, encounter_id, lambda e: engine.sign(db, e))


@router.post("/{encounter_id}/denial")
def denial(body: DenialIn, encounter_id: str = ENC_ID, db: Session = Depends(get_db)) -> dict:
    return _run(db, encounter_id, lambda e: engine.resolve_denial(db, e, body.action))


@router.post("/{encounter_id}/patient-payment")
def patient_payment(body: PaymentIn, encounter_id: str = ENC_ID, db: Session = Depends(get_db)) -> dict:
    return _run(db, encounter_id, lambda e: engine.record_patient_payment(db, e, body.amount))


# --------------------------------------------------------------------------- serialization


def _load(db: Session, encounter_id: str) -> Encounter:
    enc = engine.get_encounter(db, encounter_id)
    if enc is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Encounter not found")
    return enc


def _run(db: Session, encounter_id: str, fn) -> dict:
    enc = _load(db, encounter_id)
    try:
        fn(enc)
    except PipelineError as e:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, str(e)) from e
    return detail(enc)


def summary(e: Encounter) -> dict:
    doctor = cat.DOCTOR_BY_ID[e.doctor_id]
    return {
        "id": e.id, "patient_name": e.patient_name, "doctor": doctor.name, "specialty": doctor.specialty,
        "provider": cat.PROVIDER_INFO[e.provider_id]["name"], "payer": cat.PAYER_INFO[e.payer_id]["name"],
        "payer_id": e.payer_id, "scheduled_at": e.scheduled_at.isoformat(timespec="minutes"), "visit_reason": e.visit_reason,
        "stage": e.stage, "step": Stage.step(e.stage), "attention": e.attention, "attention_detail": e.attention_detail,
        "claim_status": e.claim_status, "total_charge": e.total_charge, "payer_paid": e.payer_paid,
        "patient_paid": e.patient_paid, "balance": e.balance, "sim_day": e.sim_day,
    }


def detail(e: Encounter) -> dict:
    doctor = cat.DOCTOR_BY_ID[e.doctor_id]
    plan = cat.PLANS[e.payer_id]
    return summary(e) | {
        "patient": {"name": e.patient_name, "patient_id": e.patient_id, "birth_year": e.birth_year, "sex": e.sex,
                    "state": e.state, "new_patient": e.new_patient},
        "insurance": {"payer_id": e.payer_id, "payer": cat.PAYER_INFO[e.payer_id]["name"],
                      "payer_type": cat.PAYER_INFO[e.payer_id]["payer_type"], "plan_name": plan.plan_name,
                      "member_id": e.member_id, "member_id_example": plan.member_id_example},
        "doctor_info": {"id": doctor.id, "name": doctor.name, "specialty": doctor.specialty, "npi": doctor.npi,
                        "primary_care": doctor.primary_care},
        "signed": e.signed, "submission_count": e.submission_count,
        "eligibility": e.eligibility, "checkin": e.checkin, "transcript": e.transcript or [], "note": e.note,
        "coding": {k: v for k, v in (e.coding or {}).items() if k != "cost_share"} or None,
        "scrub": e.scrub, "clearinghouse": e.clearinghouse or [], "adjudication": e.adjudication,
        "remittance": e.remittance or [], "appeal": e.appeal, "billing": e.billing,
        "lines": [{
            "line_no": ln.line_no, "code": ln.code, "code_system": ln.code_system, "description": ln.description,
            "category": ln.category, "modifier": ln.modifier, "units": ln.units, "dx_codes": ln.dx_codes or [],
            "charge": ln.charge, "source": ln.source, "confidence": ln.confidence, "evidence": ln.evidence,
            "rationale": ln.rationale, "coverage_status": ln.coverage_status, "coverage_reason": ln.coverage_reason,
            "auth_status": ln.auth_status, "auth_number": ln.auth_number, "billing_decision": ln.billing_decision,
            "est_payer": ln.est_payer, "est_patient": ln.est_patient, "line_status": ln.line_status, "allowed": ln.allowed,
            "payer_paid": ln.payer_paid, "patient_resp": ln.patient_resp, "adjustment": ln.adjustment, "carc": ln.carc,
            "claim_id": ln.claim_id, "cost_share": ((e.coding or {}).get("cost_share") or {}).get(str(ln.line_no)),
        } for ln in e.lines],
        "totals": {"total_charge": e.total_charge, "payer_paid": e.payer_paid, "patient_responsibility": e.patient_responsibility,
                   "patient_paid": e.patient_paid, "adjustments": e.adjustments, "balance": e.balance},
        "metrics": {"human_actions": e.human_actions, "automated_steps": e.automated_steps, "sim_day": e.sim_day},
        "events": [{"id": ev.id, "step": ev.step, "actor": ev.actor, "title": ev.title, "detail": ev.detail, "level": ev.level,
                    "automated": ev.automated, "sim_day": ev.sim_day, "at": ev.at.isoformat(timespec="seconds") if ev.at else None}
                   for ev in e.events],
    }
