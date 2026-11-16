"""Patient-journey orchestrator: the 15-step workflow as a state machine with an autopilot.

    book() -------------- steps 1-4 (booking, registration, 270/271 eligibility, prior-auth check)
    advance() ----------- runs exactly the next step for the encounter's stage
    autopilot() --------- calls advance() until a human decision is needed or the account closes

The autopilot stops only where a person must act (`Attention`): fixing coverage at the front desk,
holding the consultation, the physician signing the note and codes, approving an appeal, and the
patient paying their balance. Everything else (eligibility, coverage and prior auth, coding,
scrubbing, clearinghouse round-trips, rejection fixes, payer follow-up, payment posting and
reconciliation, statements, closing) runs automatically and is logged as an event.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.encounter import Attention, Encounter, EncounterEvent, EncounterLine, Stage
from app.models.rcm import Claim, ClaimStatus, ClaimStatusHistory, Denial, PatientSynthetic, Payment
from app.pipeline import catalog as cat
from app.pipeline import coding as coder
from app.pipeline import coverage, revenue, scribe
from app.pipeline.revenue import BILLABLE


class PipelineError(ValueError):
    """Invalid request for the encounter's current state (maps to HTTP 409)."""


@dataclass
class StepResult:
    advanced: bool
    message: str


# --------------------------------------------------------------------------- helpers


def _log(enc: Encounter, step: int, actor: str, title: str, detail: str | None = None, level: str = "info",
         automated: bool = True) -> None:
    enc.events.append(EncounterEvent(step=step, actor=actor, title=title[:160], detail=detail, level=level,
                                     automated=automated, sim_day=enc.sim_day, at=datetime.now()))
    if automated:
        enc.automated_steps += 1
    else:
        enc.human_actions += 1


def _dos(enc: Encounter) -> date:
    return enc.scheduled_at.date()


def _day(enc: Encounter) -> date:
    return _dos(enc) + timedelta(days=enc.sim_day)


def _evidence(enc: Encounter) -> dict[str, str]:
    return dict((enc.coding or {}).get("evidence", {}))


def _dx_codes(enc: Encounter) -> list[str]:
    return [d["code"] for d in (enc.coding or {}).get("diagnoses", [])]


def _usd(x: float) -> str:
    return f"${0.0 if abs(x) < 0.005 else x:,.2f}"


def _set_attention(enc: Encounter, attention: str | None, detail: str | None = None) -> None:
    enc.attention, enc.attention_detail = attention, (detail[:300] if detail else None)


def _recompute(enc: Encounter) -> None:
    live = [ln for ln in enc.lines if ln.billing_decision != "do_not_perform"]
    enc.total_charge = round(sum(ln.charge * ln.units for ln in live), 2)
    enc.payer_paid = round(sum(ln.payer_paid for ln in live), 2)
    enc.patient_responsibility = round(sum(ln.patient_resp for ln in live), 2)
    enc.adjustments = round(sum(ln.adjustment for ln in live), 2)
    enc.balance = round(enc.total_charge - enc.payer_paid - enc.adjustments - enc.patient_paid, 2)


def _price(enc: Encounter) -> dict:
    """Re-run pricing on the lines and store per-line cost share on the coding document."""
    dicts = [{"code": ln.code, "charge": ln.charge, "units": ln.units, "category": ln.category,
              "billing_decision": ln.billing_decision} for ln in enc.lines]
    totals = coverage.price_lines(dicts, enc.payer_id, enc.eligibility)
    shares = {}
    for ln, d in zip(enc.lines, dicts):
        ln.allowed, ln.est_payer, ln.est_patient = d["allowed"], d["est_payer"], d["est_patient"]
        shares[str(ln.line_no)] = d["cost_share"]
    enc.coding = {**(enc.coding or {}), "cost_share": shares, "estimate": totals}
    return totals


def next_seq(db: Session) -> int:
    return (db.scalar(select(func.max(Encounter.seq))) or 0) + 1


def get_encounter(db: Session, encounter_id: str) -> Encounter | None:
    return db.get(Encounter, encounter_id)


# --------------------------------------------------------------------------- steps 1-4: booking


def book(db: Session, *, patient_name: str, birth_year: int, sex: str, state: str, payer_id: str, member_id: str,
         doctor_id: str, scheduled_at: datetime, visit_reason: str, new_patient: bool) -> Encounter:
    doctor = cat.DOCTOR_BY_ID.get(doctor_id)
    if doctor is None:
        raise PipelineError("Unknown doctor")
    if payer_id not in cat.PLANS:
        raise PipelineError("Unknown insurance plan")
    clash = db.scalar(select(Encounter.id).where(Encounter.doctor_id == doctor_id, Encounter.scheduled_at == scheduled_at))
    if clash:
        raise PipelineError(f"{doctor.name} already has an appointment at that time")

    seq = next_seq(db)
    patient = PatientSynthetic(id=f"PAT-E{seq:05d}", birth_year=birth_year, sex=sex, state=state, primary_payer_id=payer_id)
    db.add(patient)
    db.flush()  # no ORM relationship orders the inserts, so persist the patient first
    enc = Encounter(
        id=f"ENC-{seq:06d}", seq=seq, patient_name=patient_name.strip(), patient_id=patient.id, birth_year=birth_year,
        sex=sex, state=state.upper(), payer_id=payer_id, member_id=member_id.strip().upper(), provider_id=doctor.provider_id,
        doctor_id=doctor_id, new_patient=new_patient, scheduled_at=scheduled_at, visit_reason=visit_reason.strip(),
        stage=Stage.BOOKED, claim_status="draft", submission_count=0, signed=False, sim_day=0,
        human_actions=0, automated_steps=0, total_charge=0, payer_paid=0, patient_responsibility=0,
        patient_paid=0, adjustments=0, balance=0,
    )
    db.add(enc)
    _log(enc, 1, "patient", "Appointment booked",
         f"{doctor.name} ({doctor.specialty}) on {scheduled_at:%a %b %d, %Y at %I:%M %p}. Reason: {enc.visit_reason}.", automated=False)
    enc.stage = Stage.REGISTERED
    _log(enc, 2, "system", "Patient and insurance registered",
         f"{'New' if new_patient else 'Established'} patient, born {birth_year}, {state.upper()}. "
         f"{cat.PAYER_INFO[payer_id]['name']} member {enc.member_id}.", "success")
    _verify(enc)
    db.commit()
    return enc


def _verify(enc: Encounter) -> None:
    doctor = cat.DOCTOR_BY_ID[enc.doctor_id]
    elig = coverage.verify_eligibility(enc.payer_id, enc.member_id, _dos(enc), specialist=not doctor.primary_care)
    enc.eligibility = elig
    if not elig["active"]:
        enc.stage = Stage.REGISTERED
        _set_attention(enc, Attention.ELIGIBILITY, f"{elig['error']}: {elig['message']}")
        _log(enc, 3, "payer", f"Eligibility failed: {elig['error']}", f"271 response {elig['error_code']}. {elig['message']}", "error")
        return
    _set_attention(enc, None)
    enc.stage = Stage.ELIGIBILITY_VERIFIED
    _log(enc, 3, "payer", "Eligibility verified (270/271)",
         f"{elig['plan_name']} active. Copay {_usd(elig['copay'])} ({elig['copay_type']}), deductible "
         f"{_usd(elig['deductible_remaining'])} remaining of {_usd(elig['deductible'])}, coinsurance {elig['coinsurance_pct']}%.",
         "success")
    pa = coverage.planned_service_auth(enc.visit_reason, enc.payer_id)
    enc.checkin = {**(enc.checkin or {}), "planned_auth": pa}
    enc.stage = Stage.AUTHORIZATION_CHECKED
    _log(enc, 4, "ai", "Prior authorization check", pa["message"]
         + (f" Services: {', '.join(pa['services'])}." if pa["services"] else ""), "warning" if pa["required"] else "success")


def update_registration(db: Session, enc: Encounter, member_id: str, payer_id: str | None) -> Encounter:
    if enc.stage not in (Stage.REGISTERED, Stage.ELIGIBILITY_VERIFIED, Stage.AUTHORIZATION_CHECKED):
        raise PipelineError("Insurance can only be changed before check-in")
    if payer_id:
        if payer_id not in cat.PLANS:
            raise PipelineError("Unknown insurance plan")
        enc.payer_id = payer_id
        db.get(PatientSynthetic, enc.patient_id).primary_payer_id = payer_id
    enc.member_id = member_id.strip().upper()
    _log(enc, 2, "front_desk", "Insurance details corrected", f"{cat.PAYER_INFO[enc.payer_id]['name']} member {enc.member_id}.",
         automated=False)
    _verify(enc)
    db.commit()
    return enc


# --------------------------------------------------------------------------- steps 5-9: visit


def _check_in(enc: Encounter) -> StepResult:
    elig = enc.eligibility or {}
    ptype = cat.PAYER_INFO[enc.payer_id]["payer_type"]
    copay = float(elig.get("copay", 0)) if ptype in ("commercial", "medicare_advantage") else 0.0
    enc.checkin = {**(enc.checkin or {}), "checked_in_at": datetime.now().isoformat(timespec="minutes"), "copay_collected": copay}
    enc.patient_paid = round(enc.patient_paid + copay, 2)
    if copay:
        enc.billing = {**(enc.billing or {}), "payments": [*(enc.billing or {}).get("payments", []),
                                                        {"date": _day(enc).isoformat(), "amount": copay, "method": "card", "note": "Copay at check-in"}]}
    enc.stage = Stage.CHECKED_IN
    _log(enc, 5, "front_desk", "Patient checked in",
         f"Copay of {_usd(copay)} collected at the front desk." if copay else "No copay due at check-in for this plan.", "success")
    return StepResult(True, "Checked in")


def _start_consultation(enc: Encounter) -> StepResult:
    enc.stage = Stage.IN_CONSULTATION
    _set_attention(enc, Attention.CONSULTATION, "Doctor and patient are in the room: start the AI scribe, or paste the conversation.")
    _log(enc, 6, "ai", "AI scribe ready", "Listening for the doctor-patient conversation (speech-to-text in the exam room).")
    return StepResult(True, "Consultation started")


def save_transcript(db: Session, enc: Encounter, utterances: list[dict]) -> Encounter:
    if enc.stage not in (Stage.CHECKED_IN, Stage.IN_CONSULTATION):
        raise PipelineError("The transcript can only be recorded during the consultation")
    if enc.stage == Stage.CHECKED_IN:
        _start_consultation(enc)
    parsed = scribe.normalize_utterances(utterances)
    enc.transcript = [{"speaker": u.speaker, "text": u.text} for u in parsed]
    db.commit()
    return enc


def run_scribe(db: Session, enc: Encounter) -> Encounter:
    """End of the consultation: note (7), superbill (8), coding + coverage + prior auth (9)."""
    if enc.stage != Stage.IN_CONSULTATION:
        raise PipelineError("The consultation is not in progress")
    utts = scribe.normalize_utterances(enc.transcript or [])
    if not utts:
        raise PipelineError("No conversation captured yet")
    _log(enc, 6, "doctor", "Consultation completed", f"{len(utts)} utterances captured by the AI scribe.", automated=False)

    res = scribe.extract(utts)
    age = _dos(enc).year - enc.birth_year
    coded = coder.code_encounter(res, payer_id=enc.payer_id, new_patient=enc.new_patient, age=age)
    note = scribe.build_note(res, enc.visit_reason, coded.diagnoses, [ln for ln in coded.lines if ln["category"] != "em"])
    enc.note = note
    enc.stage = Stage.DOCUMENTED
    _log(enc, 7, "ai", "AI scribe drafted the SOAP note",
         f"{len(note['subjective']['hpi'])} history statements, {len(note['objective']['exam'])} exam findings, "
         f"{len(note['not_coded'])} findings held back (negated/uncertain).", "success")

    for ln in list(enc.lines):
        enc.lines.remove(ln)
    db.flush()
    dx_codes = [d["code"] for d in coded.diagnoses]
    for i, d in enumerate(coded.lines, 1):
        cov = coverage.determine_coverage(d, enc.payer_id, dx_codes, res.evidence)
        d.update(cov)
    auths = coverage.request_authorizations(coded.lines, enc.payer_id, dx_codes, res.evidence, enc.id)
    for i, d in enumerate(coded.lines, 1):
        enc.lines.append(EncounterLine(
            line_no=i, code=d["code"], code_system=d["code_system"], description=d["description"], category=d["category"],
            modifier=d["modifier"], units=d["units"], dx_codes=d["dx_codes"], charge=d["charge"], source=d["source"],
            confidence=d["confidence"], evidence=d["evidence"], rationale=d["rationale"],
            coverage_status=d["coverage_status"], coverage_reason=d["coverage_reason"],
            auth_status=d.get("auth_status") or ("not_required" if d["coverage_status"] != "prior_auth_required" else None),
            auth_number=d.get("auth_number"), billing_decision=d["billing_decision"],
            line_status="not_performed" if d["billing_decision"] == "do_not_perform" else "draft",
            allowed=0, payer_paid=0, patient_resp=0, adjustment=0, est_payer=0, est_patient=0,
        ))
    enc.stage = Stage.CHARGES_CAPTURED
    _log(enc, 8, "ai", f"Superbill: {len(coded.lines)} charges captured",
         ", ".join(f"{d['code']} {_usd(d['charge'])}" for d in coded.lines), "success")

    enc.coding = {"diagnoses": coded.diagnoses, "em": coded.em, "warnings": coded.warnings, "evidence": res.evidence}
    totals = _price(enc)
    enc.stage = Stage.CODED
    enc.signed = False
    _log(enc, 9, "ai", f"AI coded {len(coded.diagnoses)} ICD-10-CM and {len(coded.lines)} CPT/HCPCS codes",
         "Diagnoses: " + (", ".join(d["code"] for d in coded.diagnoses) or "none") + ". E/M: "
         + " + ".join(x for x in (coded.em.get("preventive_code"), coded.em.get("code")) if x) + f" (MDM {coded.em['mdm']}).",
         "success" if coded.diagnoses else "warning")
    for a in auths:
        _log(enc, 4, "payer", f"Prior authorization {a['status']} for {a['code']}", a["detail"],
             "success" if a["status"] == "approved" else "error")
    counts: dict[str, int] = {}
    for ln in enc.lines:
        counts[ln.coverage_status] = counts.get(ln.coverage_status, 0) + 1
    flagged = [ln for ln in enc.lines if ln.coverage_status in ("not_covered", "medical_necessity_risk") or ln.auth_status == "denied"]
    _log(enc, 9, "ai", "Insurance coverage checked for every service",
         ", ".join(f"{v} {k.replace('_', ' ')}" for k, v in counts.items())
         + f". Estimated insurance pays {_usd(totals['payer'])}, patient pays {_usd(totals['patient'])}.",
         "warning" if flagged else "success")
    for ln in flagged:
        _log(enc, 9, "ai", f"{ln.code} {'will not be covered' if ln.coverage_status == 'not_covered' or ln.auth_status == 'denied' else 'is at risk of denial'}",
             f"{ln.coverage_reason} Decision: {ln.billing_decision.replace('_', ' ')}.", "warning")
    low = [ln.code for ln in enc.lines if ln.confidence < 0.8]
    _set_attention(enc, Attention.SIGN_OFF,
                   "Physician review: sign the note and codes" + (f" (low-confidence: {', '.join(low)})" if low else "."))
    _recompute(enc)
    db.commit()
    return enc


def _line_from_code(code: str) -> dict:
    if code in cat.EM_CODES:
        desc, charge = cat.EM_CODES[code]
        return {"code": code, "code_system": "HCPCS" if code[0].isalpha() else "CPT", "description": desc, "category": "em", "charge": charge}
    svc = cat.SERVICE_BY_CODE.get(code)
    if svc is None:
        raise PipelineError(f"Unknown code {code}")
    return {"code": code, "code_system": svc.system, "description": svc.description, "category": svc.category, "charge": svc.charge}


def dx_lookup() -> dict[str, str]:
    out = {}
    for c in cat.CONDITIONS:
        out[c.code] = c.description
        for code, desc in (c.lateral or {}).values():
            out[code] = desc
    return out


def edit_coding(db: Session, enc: Encounter, diagnoses: list[str], lines: list[dict]) -> Encounter:
    """Doctor/coder edits before sign-off. Coverage, authorization and pricing are recomputed."""
    if enc.stage != Stage.CODED or enc.signed:
        raise PipelineError("Codes can only be edited before the physician signs")
    known = dx_lookup()
    bad = [c for c in diagnoses if c not in known]
    if bad:
        raise PipelineError(f"Unknown diagnosis code(s): {', '.join(bad)}")
    if not diagnoses:
        raise PipelineError("At least one diagnosis is required")
    old_dx = {d["code"]: d for d in (enc.coding or {}).get("diagnoses", [])}
    new_dx = [old_dx.get(c) or {"code": c, "description": known[c], "confidence": 1.0, "evidence": None,
                                "rationale": "Added by the physician", "kind": "manual"} for c in diagnoses]
    for i, d in enumerate(new_dx):
        d["primary"] = i == 0
    evidence = _evidence(enc)
    old_lines = {ln.code: ln for ln in enc.lines}
    for ln in list(enc.lines):
        enc.lines.remove(ln)
    db.flush()
    for i, item in enumerate(lines, 1):
        base = _line_from_code(item["code"])
        prev = old_lines.get(item["code"])
        svc = cat.SERVICE_BY_CODE.get(base["code"])
        nec = coder.necessity(svc, diagnoses, evidence) if svc else None
        if base["category"] == "em":
            ptrs = [c for c in diagnoses if not c.startswith("Z23")][:4] or diagnoses[:1]
        elif svc:
            ptrs = coder._pointers(svc, new_dx, evidence)
        else:
            ptrs = diagnoses[:1]
        if prev is not None and prev.rationale:
            rationale = prev.rationale  # the coder's original reasoning (already states necessity)
        else:
            rationale = "Added by the physician"
            if nec is not None:
                rationale += f". Medical necessity: supported by {nec.via}" if nec.supported else \
                    f". Medical necessity NOT established: {nec.missing}"
        d = base | {"modifier": (item.get("modifier") or "").upper().strip() or None, "units": int(item.get("units") or 1), "dx_codes": ptrs}
        cov = coverage.determine_coverage(d, enc.payer_id, diagnoses, evidence)
        decision = item.get("billing_decision") or cov["billing_decision"]
        ln = EncounterLine(
            line_no=i, code=d["code"], code_system=d["code_system"], description=d["description"], category=d["category"],
            modifier=d["modifier"], units=d["units"], dx_codes=ptrs, charge=d["charge"],
            source=prev.source if prev else "manual", confidence=prev.confidence if prev else 1.0,
            evidence=prev.evidence if prev else None,
            rationale=rationale,
            coverage_status=cov["coverage_status"], coverage_reason=cov["coverage_reason"],
            auth_status=prev.auth_status if prev and cov["coverage_status"] == "prior_auth_required" else
            ("not_required" if cov["coverage_status"] != "prior_auth_required" else None),
            auth_number=prev.auth_number if prev and cov["coverage_status"] == "prior_auth_required" else None,
            billing_decision=decision, line_status="not_performed" if decision == "do_not_perform" else "draft",
            allowed=0, payer_paid=0, patient_resp=0, adjustment=0, est_payer=0, est_patient=0,
        )
        enc.lines.append(ln)
    pending = [{"code": ln.code, "coverage_status": ln.coverage_status} for ln in enc.lines
               if ln.coverage_status == "prior_auth_required" and ln.auth_status is None]
    for res in coverage.request_authorizations(pending, enc.payer_id, diagnoses, evidence, enc.id):
        for ln in enc.lines:
            if ln.code == res["code"]:
                ln.auth_status, ln.auth_number = res["status"], res["auth_number"]
                requested = next((x for x in lines if x["code"] == ln.code), {})
                if not requested.get("billing_decision"):
                    ln.billing_decision = "bill_insurance" if res["status"] == "approved" else "do_not_perform"
                    ln.line_status = "draft" if res["status"] == "approved" else "not_performed"
        _log(enc, 4, "payer", f"Prior authorization {res['status']} for {res['code']}", res["detail"],
             "success" if res["status"] == "approved" else "error")
    enc.coding = {**(enc.coding or {}), "diagnoses": new_dx}
    _price(enc)
    _recompute(enc)
    _log(enc, 9, "doctor", "Codes reviewed and edited",
         f"Diagnoses: {', '.join(diagnoses)}. Services: {', '.join(ln.code + (('-' + ln.modifier.replace(' ', '-')) if ln.modifier else '') for ln in enc.lines)}.",
         automated=False)
    db.commit()
    return enc


def sign(db: Session, enc: Encounter) -> Encounter:
    if enc.stage != Stage.CODED or enc.signed:
        raise PipelineError("Nothing to sign")
    if not _dx_codes(enc):
        raise PipelineError("Add at least one diagnosis before signing")
    enc.signed = True
    doctor = cat.DOCTOR_BY_ID[enc.doctor_id]
    _set_attention(enc, None)
    _log(enc, 9, "doctor", "Note and codes signed", f"Electronically signed by {doctor.name}.", "success", automated=False)
    db.commit()
    return enc


# --------------------------------------------------------------------------- steps 10-15: claim to cash


def _scrub(db: Session, enc: Encounter) -> StepResult:
    if not revenue.billed_lines(enc):
        enc.scrub = {"clean": True, "checks": [], "claim_form": None, "transaction": None, "auto_fixes": 0, "billed_lines": 0,
                     "total_billed": 0, "note": "No services billed to insurance."}
        enc.claim_status = "none"
        enc.stage = Stage.PAYMENT_POSTED
        _log(enc, 10, "ai", "No insurance claim needed", "Every service is self-pay or was not performed; going straight to patient billing.")
        _self_pay_adjust(enc)
        _recompute(enc)
        return StepResult(True, "No claim")
    report = revenue.scrub(enc, _evidence(enc))
    enc.scrub = report
    _price(enc)
    enc.sim_day = max(enc.sim_day, 1)
    if not report["clean"]:
        fails = "; ".join(c["detail"] for c in report["checks"] if c["status"] == "fail")
        _set_attention(enc, Attention.SCRUB, f"Claim scrubber found errors: {fails}")
        _log(enc, 10, "ai", "Claim scrubber found errors", fails, "error")
        return StepResult(False, "Scrub failed")
    enc.claim_status = "scrubbed"
    enc.stage = Stage.CLAIM_SCRUBBED
    _log(enc, 10, "ai", f"Claim built ({report['claim_form']} / {report['transaction']}) and scrubbed clean",
         f"{report['billed_lines']} lines, {_usd(report['total_billed'])} billed. "
         + (f"{report['auto_fixes']} issue(s) auto-corrected before submission." if report["auto_fixes"] else "No corrections needed."),
         "success")
    return StepResult(True, "Scrubbed")


def _submit(db: Session, enc: Encounter) -> StepResult:
    attempt = enc.submission_count + 1
    sub = revenue.clearinghouse_submit(enc, attempt)
    enc.clearinghouse = [*(enc.clearinghouse or []), sub]
    enc.submission_count = attempt
    enc.stage = Stage.SUBMITTED
    for ln in revenue.billed_lines(enc):
        ln.line_status = "submitted"
    _log(enc, 11, "clearinghouse", f"Claim submitted via clearinghouse (attempt {attempt})",
         "Translated to X12, validated and routed. 999: file accepted.")
    ack = sub["ack_277ca"]
    if ack["status"] == "rejected":
        enc.claim_status = "rejected"
        _log(enc, 11, "payer", f"277CA rejection ({ack['category_code']})",
             f"{ack['detail']}. The claim never entered the payer's system: correct and resubmit.", "error")
    else:
        enc.claim_status = "accepted"
        _log(enc, 11, "payer", "277CA: accepted for adjudication", f"Payer claim number {ack['payer_icn']}.", "success")
    _sync_claims(db, enc)
    return StepResult(True, "Submitted")


def _fix_rejection(db: Session, enc: Encounter) -> StepResult:
    ack = enc.clearinghouse[-1]["ack_277ca"]
    _log(enc, 11, "ai", "Rejection corrected automatically", ack.get("auto_fix") or "Corrected the rejected field.", "success")
    enc.sim_day += 1
    return _submit(db, enc)


def _adjudicate(db: Session, enc: Encounter) -> StepResult:
    plan = cat.PLANS[enc.payer_id]
    adj = dict(enc.adjudication or {})
    if enc.claim_status == "pended":
        adj["records_sent"] = True
        enc.adjudication = adj
        enc.claim_status = "accepted"
        enc.sim_day += 3
        _log(enc, 12, "ai", "Records sent to the payer (275 attachment)",
             "The signed visit note and orders were attached automatically, referencing the payer claim number.", "success")
    if revenue.should_pend(enc):
        enc.claim_status = "pended"
        enc.sim_day += plan.adjudication_days // 2
        enc.adjudication = {**adj, "pended": True, "pend_reason": "Additional documentation requested (RARC M127)"}
        _log(enc, 12, "payer", "Claim pended: payer requested medical records",
             "277 status: additional information requested (RARC M127). On hold until records arrive.", "warning")
        _sync_claims(db, enc)
        return StepResult(True, "Pended")

    evidence = _evidence(enc)
    result = revenue.adjudicate(enc, evidence)
    enc.sim_day += plan.adjudication_days
    enc.adjudication = {**adj, **result, "adjudication_date": _day(enc).isoformat()}
    shares = (enc.coding or {}).get("cost_share", {})
    for ln in revenue.billed_lines(enc):
        billed = round(ln.charge * ln.units, 2)
        if ln.line_status == "paid":
            ln.payer_paid, ln.patient_resp = ln.est_payer, ln.est_patient
            ln.adjustment = round(billed - ln.allowed, 2)
        elif ln.carc == "PR-50":
            ln.payer_paid, ln.patient_resp = 0.0, ln.allowed
            ln.adjustment = round(billed - ln.allowed, 2)
            shares[str(ln.line_no)] = {"deductible": 0, "copay": 0, "coinsurance": 0, "abn_liability": ln.allowed}
        else:  # CO denial: nothing paid, nothing billable to the patient until appealed or written off
            ln.payer_paid, ln.patient_resp, ln.adjustment = 0.0, 0.0, 0.0
    enc.coding = {**(enc.coding or {}), "cost_share": shares}
    enc.claim_status = "adjudicated"
    enc.stage = Stage.ADJUDICATED
    paid = sum(ln.payer_paid for ln in revenue.billed_lines(enc))
    fails = [g["gate"] for g in result["gates"] if g["status"] == "fail"]
    _log(enc, 12, "payer", f"Adjudicated: {result['outcome'].replace('_', ' ')}",
         f"Five gates: {'all passed' if not fails else 'failed ' + ', '.join(fails)}. "
         f"Payer will pay {_usd(paid)}" + (f"; denied {', '.join(result['denied_lines'])}." if result["denied_lines"] else "."),
         "success" if result["outcome"] == "paid" else "warning")
    _recompute(enc)
    _sync_claims(db, enc)
    return StepResult(True, "Adjudicated")


def _post_payment(db: Session, enc: Encounter) -> StepResult:
    enc.sim_day += 2
    lines = revenue.billed_lines(enc)
    era = revenue.build_era(enc, lines, _day(enc))
    expected = round(sum(ln.est_payer for ln in lines if ln.line_status == "paid"), 2)
    variance = round(era["total_paid"] - expected, 2)
    era["reconciliation"] = {"expected": expected, "paid": era["total_paid"], "variance": variance,
                             "status": "matched" if abs(variance) < 0.01 else "underpaid" if variance < 0 else "overpaid"}
    enc.remittance = [*(enc.remittance or []), era]
    _self_pay_adjust(enc)
    enc.stage = Stage.PAYMENT_POSTED
    if era["total_paid"] > 0:
        _log(enc, 13, "payer", f"ERA 835 received; {_usd(era['total_paid'])} deposited by EFT",
             f"EFT trace {era['eft_trace']} matched to the ERA (reassociation). Posted to {len(lines)} line(s).", "success")
    else:
        _log(enc, 13, "payer", "ERA 835 received: no payment on this claim",
             f"Adjustments posted to {len(lines)} line(s); see the denial handling below.", "warning")
    _log(enc, 13, "ai", "Payment reconciled against the contract",
         f"Expected {_usd(expected)}, paid {_usd(era['total_paid'])}: "
         + ("no underpayment." if abs(variance) < 0.01 else f"variance {_usd(variance)} flagged for a payment dispute."),
         "success" if abs(variance) < 0.01 else "warning")
    _recompute(enc)
    _sync_claims(db, enc)
    return StepResult(True, "Payment posted")


def _self_pay_adjust(enc: Encounter) -> None:
    for ln in enc.lines:
        if ln.billing_decision == "self_pay" and ln.line_status != "self_pay":
            ln.line_status = "self_pay"
            ln.patient_resp = ln.est_patient
            ln.adjustment = round(ln.charge * ln.units - ln.est_patient, 2)


def _open_denials(enc: Encounter) -> list[EncounterLine]:
    resolved = {int(k) for k in ((enc.appeal or {}).get("resolutions") or {})}
    return [ln for ln in enc.lines if ln.line_status == "denied" and ln.line_no not in resolved]


def _handle_denials(db: Session, enc: Encounter) -> StepResult | None:
    evidence = _evidence(enc)
    for ln in _open_denials(enc):
        assessment = revenue.appeal_assessment(ln, evidence)
        if not assessment["recommend"]:
            _resolve(enc, ln, "patient_responsibility" if ln.carc.startswith("PR") else "write_off", assessment)
            continue
        letter = revenue.draft_appeal(enc, ln, evidence, assessment)
        enc.appeal = {**(enc.appeal or {}), "line_no": ln.line_no, "code": ln.code, "carc": ln.carc,
                      "assessment": assessment, "letter": letter, "status": "drafted"}
        _set_attention(enc, Attention.DENIAL,
                       f"{ln.code} denied ({ln.carc}). AI drafted an appeal (success likelihood {assessment['likelihood']}): approve it or accept the denial.")
        _log(enc, 13, "ai", f"Denial on {ln.code} ({ln.carc}): appeal drafted",
             f"Categorized as {'authorization' if ln.carc == 'CO-197' else 'medical necessity'}. {assessment['reason']}", "warning")
        _sync_claims(db, enc)
        return StepResult(True, "Appeal drafted")
    return None


def _resolve(enc: Encounter, ln: EncounterLine, how: str, assessment: dict) -> None:
    billed = round(ln.charge * ln.units, 2)
    if how == "patient_responsibility":
        detail = f"Signed ABN on file: {_usd(ln.patient_resp)} moved to the patient's balance. {assessment['reason']}"
        title = f"{ln.code} denial routed to the patient (ABN)"
    else:
        ln.adjustment, ln.patient_resp = billed, 0.0
        detail = "Provider liability (CO): written off; this cannot be billed to the patient."
        title = f"{ln.code} denial written off"
    prevent = {"CO-197": "Prevent upstream: request authorization at ordering (the coverage check now does this automatically).",
               "CO-50": "Prevent upstream: document necessity findings before ordering, or offer the patient the self-pay price.",
               "PR-50": "Prevent upstream: the ABN protected the practice; keep issuing it for services Medicare may deny."}
    enc.appeal = {**(enc.appeal or {}), "resolutions": {**((enc.appeal or {}).get("resolutions") or {}),
                                                        str(ln.line_no): {"code": ln.code, "carc": ln.carc, "resolution": how}}}
    _log(enc, 13, "ai", title, f"{detail} {prevent.get(ln.carc, '')}", "info")


def resolve_denial(db: Session, enc: Encounter, action: str) -> Encounter:
    appeal = dict(enc.appeal or {})
    if enc.attention != Attention.DENIAL or appeal.get("status") != "drafted":
        raise PipelineError("No denial is waiting for a decision")
    ln = next(x for x in enc.lines if x.line_no == appeal["line_no"])
    if action == "appeal":
        _log(enc, 13, "coder", f"Appeal approved and sent for {ln.code}", "Reconsideration request with the visit note attached.",
             automated=False)
        enc.sim_day += 30
        outcome = revenue.appeal_outcome(appeal["assessment"])
        appeal["status"] = outcome
        enc.appeal = appeal
        if outcome == "overturned":
            # Reprice the line as payable and pay it on a second ERA.
            saved = ln.billing_decision
            ln.billing_decision = "bill_insurance"
            _price(enc)
            ln.billing_decision = saved
            ln.line_status, ln.carc = "paid", None
            ln.payer_paid, ln.patient_resp = ln.est_payer, ln.est_patient
            ln.adjustment = round(ln.charge * ln.units - ln.allowed, 2)
            era = revenue.build_era(enc, [ln], _day(enc), kind="appeal")
            era["reconciliation"] = {"expected": ln.est_payer, "paid": era["total_paid"], "variance": 0.0, "status": "matched"}
            enc.remittance = [*(enc.remittance or []), era]
            enc.appeal = {**enc.appeal, "resolutions": {**(enc.appeal.get("resolutions") or {}),
                                                        str(ln.line_no): {"code": ln.code, "carc": appeal["carc"], "resolution": "overturned"}}}
            _log(enc, 13, "payer", f"Appeal overturned: {_usd(ln.payer_paid)} paid for {ln.code}",
                 f"Second ERA, EFT trace {era['eft_trace']}.", "success")
        else:
            _log(enc, 13, "payer", f"Appeal upheld for {ln.code}", "The payer maintained the denial.", "warning")
            _resolve(enc, ln, "write_off" if ln.carc.startswith("CO") else "patient_responsibility", appeal["assessment"])
    elif action == "accept":
        appeal["status"] = "accepted"
        enc.appeal = appeal
        _log(enc, 13, "coder", f"Denial accepted for {ln.code}", None, automated=False)
        _resolve(enc, ln, "write_off" if ln.carc.startswith("CO") else "patient_responsibility", appeal["assessment"])
    else:
        raise PipelineError("action must be 'appeal' or 'accept'")
    _set_attention(enc, None)
    _recompute(enc)
    _sync_claims(db, enc)
    db.commit()
    return enc


def _bill_patient(db: Session, enc: Encounter) -> StepResult:
    enc.sim_day += 1
    stmt = revenue.build_statement(enc, _day(enc))
    if stmt["credit"] > 0:
        refund = stmt["credit"]
        enc.patient_paid = round(enc.patient_paid - refund, 2)
        enc.billing = {**(enc.billing or {}), "payments": [*(enc.billing or {}).get("payments", []),
                                                        {"date": _day(enc).isoformat(), "amount": -refund, "method": "card", "note": "Refund of overpaid copay"}]}
        _log(enc, 14, "ai", f"Overpayment refunded: {_usd(refund)}", "Copay collected at check-in exceeded the patient's final share.", "info")
        stmt = revenue.build_statement(enc, _day(enc))
    enc.billing = {**(enc.billing or {}), "statement": stmt}
    enc.stage = Stage.PATIENT_BILLED
    _recompute(enc)
    if stmt["balance_due"] > 0.004:
        _set_attention(enc, Attention.PATIENT_PAYMENT, f"Patient statement sent: {_usd(stmt['balance_due'])} due by {stmt['due_date']}.")
        _log(enc, 14, "ai", f"Patient statement sent: {_usd(stmt['balance_due'])} due",
             f"{len(stmt['items'])} item(s). EOB explains what insurance covered; pay online or set up a payment plan.", "info")
    else:
        _log(enc, 14, "ai", "No patient balance", "Insurance and the check-in copay covered everything.", "success")
    _sync_claims(db, enc)
    return StepResult(True, "Patient billed")


def record_patient_payment(db: Session, enc: Encounter, amount: float | None) -> Encounter:
    if enc.stage != Stage.PATIENT_BILLED:
        raise PipelineError("No patient statement is open")
    due = round(enc.balance, 2)
    if due <= 0.004:
        raise PipelineError("Nothing is owed")
    amt = round(min(amount if amount is not None else due, due), 2)
    if amt <= 0:
        raise PipelineError("Amount must be positive")
    enc.sim_day += 7
    enc.patient_paid = round(enc.patient_paid + amt, 2)
    enc.billing = {**(enc.billing or {}), "payments": [*(enc.billing or {}).get("payments", []),
                                                    {"date": _day(enc).isoformat(), "amount": amt, "method": "card", "note": "Patient portal payment"}]}
    _recompute(enc)
    _log(enc, 14, "patient", f"Patient paid {_usd(amt)} online", f"Remaining balance {_usd(max(enc.balance, 0))}.", "success", automated=False)
    if enc.balance <= 0.004:
        _set_attention(enc, None)
    else:
        _set_attention(enc, Attention.PATIENT_PAYMENT, f"{_usd(enc.balance)} still due.")
    _sync_claims(db, enc)
    db.commit()
    return enc


def _close(db: Session, enc: Encounter) -> StepResult:
    enc.stage = Stage.CLOSED
    _set_attention(enc, None)
    _recompute(enc)
    collected = enc.payer_paid + enc.patient_paid
    _log(enc, 15, "system", "Account closed: revenue cycle complete",
         f"Collected {_usd(collected)} (insurance {_usd(enc.payer_paid)} + patient {_usd(enc.patient_paid)}) of "
         f"{_usd(enc.total_charge)} billed; {_usd(enc.adjustments)} contractual/self-pay adjustments and write-offs. "
         f"Day {enc.sim_day} after the visit.", "success")
    _sync_claims(db, enc)
    return StepResult(True, "Closed")


# --------------------------------------------------------------------------- dispatcher


def advance(db: Session, enc: Encounter) -> StepResult:
    """Run the next step. Returns advanced=False when a human decision is needed."""
    if enc.attention:
        return StepResult(False, enc.attention_detail or enc.attention)
    s = enc.stage
    if s in (Stage.BOOKED, Stage.REGISTERED, Stage.ELIGIBILITY_VERIFIED):
        _verify(enc)
        r = StepResult(enc.attention is None, "Eligibility re-verified")
    elif s == Stage.AUTHORIZATION_CHECKED:
        r = _check_in(enc)
    elif s == Stage.CHECKED_IN:
        r = _start_consultation(enc)
    elif s == Stage.IN_CONSULTATION:
        if not enc.transcript:
            _set_attention(enc, Attention.CONSULTATION, "Capture the consultation with the AI scribe first.")
            r = StepResult(False, "Transcript needed")
        else:
            run_scribe(db, enc)
            return StepResult(True, "Scribe and coding complete")
    elif s in (Stage.DOCUMENTED, Stage.CHARGES_CAPTURED):
        _set_attention(enc, Attention.CONSULTATION, "Re-run the AI scribe.")
        enc.stage = Stage.IN_CONSULTATION
        r = StepResult(False, "Scribe incomplete")
    elif s == Stage.CODED:
        if not enc.signed:
            _set_attention(enc, Attention.SIGN_OFF, "Physician review: sign the note and codes.")
            r = StepResult(False, "Sign-off needed")
        else:
            r = _scrub(db, enc)
    elif s == Stage.CLAIM_SCRUBBED:
        r = _submit(db, enc)
    elif s == Stage.SUBMITTED:
        r = _fix_rejection(db, enc) if enc.claim_status == "rejected" else _adjudicate(db, enc)
    elif s == Stage.ADJUDICATED:
        r = _post_payment(db, enc)
    elif s == Stage.PAYMENT_POSTED:
        r = _handle_denials(db, enc) or _bill_patient(db, enc)
    elif s == Stage.PATIENT_BILLED:
        if enc.balance > 0.004:
            _set_attention(enc, Attention.PATIENT_PAYMENT, f"{_usd(enc.balance)} due from the patient.")
            r = StepResult(False, "Awaiting patient payment")
        else:
            r = _close(db, enc)
    else:
        r = StepResult(False, "Account is closed")
    db.commit()
    return r


def autopilot(db: Session, enc: Encounter, max_steps: int = 40) -> list[str]:
    done = []
    for _ in range(max_steps):
        r = advance(db, enc)
        if not r.advanced:
            break
        done.append(r.message)
        if enc.stage == Stage.CLOSED:
            break
    return done


# --------------------------------------------------------------------------- claims mirror


_CATEGORY = {"CO-50": ("medical_necessity", "50", "Non-covered: not deemed a medical necessity by the payer"),
             "PR-50": ("medical_necessity", "50", "Non-covered: not deemed a medical necessity by the payer"),
             "CO-197": ("authorization", "197", "Precertification/authorization/notification absent")}


def _sync_claims(db: Session, enc: Encounter) -> None:
    """Mirror billed lines into `claims` (one Claim per line) so they show in the Claims explorer and analytics."""
    if enc.submission_count == 0:
        return
    dos = _dos(enc)
    first = (enc.clearinghouse or [{}])[0].get("ack_277ca", {})
    was_rejected = first.get("status") == "rejected"
    adj_date = date.fromisoformat(enc.adjudication["adjudication_date"]) if (enc.adjudication or {}).get("adjudication_date") else None
    era_by_line: dict[int, list[tuple[str, float, str]]] = {}
    for era in enc.remittance or []:
        for x in era["lines"]:
            if x["paid"] > 0:
                era_by_line.setdefault(x["line_no"], []).append((era["payment_date"], x["paid"], era["eft_trace"]))
    pat_pool = max(enc.patient_paid, 0.0)
    resolutions = (enc.appeal or {}).get("resolutions") or {}
    form = cat.claim_form(enc.provider_id)[0]
    for ln in revenue.billed_lines(enc):
        if ln.line_status == "not_performed":
            continue
        cid = ln.claim_id or f"ECL-{enc.seq:06d}{ln.line_no:02d}"
        ln.claim_id = cid
        c = db.get(Claim, cid)
        if c is None:
            c = Claim(id=cid, patient_id=enc.patient_id, provider_id=enc.provider_id, payer_id=enc.payer_id,
                      claim_type="institutional" if form == "UB-04" else "professional", service_date=dos,
                      claim_date=dos + timedelta(days=1), cpt_code=ln.code, cpt_description=ln.description[:160],
                      units=ln.units, place_of_service="22" if form == "UB-04" else "11", billed_amount=round(ln.charge * ln.units, 2),
                      status=ClaimStatus.PENDING, submission_count=1)
            db.add(c)
            c.history = [ClaimStatusHistory(status="submitted", status_date=dos + timedelta(days=1), note=f"Pipeline encounter {enc.id}")]
        dx = (ln.dx_codes or [None])[0]
        c.modifier = ((ln.modifier or "").split() or [None])[0]
        c.icd10_code = dx or ""
        c.icd10_description = dx_lookup().get(dx or "", "")[:160]
        c.requires_authorization = ln.coverage_status == "prior_auth_required"
        c.authorization_number = ln.auth_number
        c.submission_count = enc.submission_count
        c.was_rejected = was_rejected
        c.rejection_reason = first.get("detail") if was_rejected else None
        c.adjudication_date = adj_date
        c.allowed_amount = ln.allowed if ln.line_status in ("paid", "denied") else 0
        c.paid_amount = ln.payer_paid
        c.patient_responsibility = ln.patient_resp
        pp = round(min(pat_pool, ln.patient_resp), 2)
        pat_pool -= pp
        c.patient_paid_amount = pp
        res = resolutions.get(str(ln.line_no), {}).get("resolution")
        c.contractual_adjustment = round(ln.adjustment if res != "write_off" else 0, 2)
        c.writeoff_amount = round(ln.adjustment if res == "write_off" else 0, 2)
        c.balance = round(max(c.billed_amount - c.paid_amount - c.patient_paid_amount - c.contractual_adjustment - c.writeoff_amount, 0), 2)
        if enc.claim_status == "rejected":
            status = ClaimStatus.REJECTED
        elif ln.line_status == "paid":
            status = ClaimStatus.PAID
        elif ln.line_status == "denied":
            status = ClaimStatus.APPEALED if (enc.appeal or {}).get("status") == "drafted" and enc.appeal.get("line_no") == ln.line_no else ClaimStatus.DENIED
        else:
            status = ClaimStatus.PENDING
        if c.history and c.history[-1].status != status:
            c.history.append(ClaimStatusHistory(status=status, status_date=_day(enc), note=f"Pipeline encounter {enc.id}"))
        c.status = status
        c.was_denied = bool(ln.carc) or res in ("write_off", "patient_responsibility", "overturned")
        c.first_pass_paid = status == ClaimStatus.PAID and not was_rejected and not c.was_denied and not (enc.adjudication or {}).get("pended")
        cat_info = _CATEGORY.get(ln.carc or (resolutions.get(str(ln.line_no), {}).get("carc") or ""))
        c.denial_reason_code, c.denial_category, c.denial_reason = (cat_info[1], cat_info[0], cat_info[2]) if cat_info else (None, None, None)
        if cat_info and not c.denials:
            carc = ln.carc or resolutions[str(ln.line_no)]["carc"]
            c.denials = [Denial(carc_code=cat_info[1], group_code=carc.split("-")[0], rarc_code=None, description=cat_info[2],
                                category=cat_info[0], denied_amount=c.billed_amount, denial_date=adj_date or _day(enc),
                                preventable=carc != "PR-50", appeal_status="not_appealed")]
        if c.denials:
            st = (enc.appeal or {}).get("status")
            d = c.denials[0]
            if res == "overturned":
                d.appeal_status, d.resolution_date = "overturned", _day(enc)
            elif st == "upheld" and (enc.appeal or {}).get("line_no") == ln.line_no:
                d.appeal_status, d.resolution_date = "upheld", _day(enc)
            elif st == "drafted" and (enc.appeal or {}).get("line_no") == ln.line_no:
                d.appeal_status = "pending"
        pays = [Payment(source="payer", amount=amt, payment_date=date.fromisoformat(pd), method="EFT", trace_number=tr)
                for pd, amt, tr in era_by_line.get(ln.line_no, [])]
        if pp > 0:
            pays.append(Payment(source="patient", amount=pp, payment_date=_day(enc), method="card", trace_number=None))
        c.payments = pays
        c.closed_date = _day(enc) if enc.stage == Stage.CLOSED and c.balance <= 0.005 else None
    db.flush()


# --------------------------------------------------------------------------- scorecard (slide 16)


def scorecard(encounters: list[Encounter]) -> dict:
    submitted = [e for e in encounters if e.submission_count > 0]
    clean = [e for e in submitted if (e.clearinghouse or [{}])[0].get("ack_277ca", {}).get("status") == "accepted"]
    adjudicated_lines = [ln for e in encounters for ln in e.lines if ln.line_status in ("paid", "denied") or ln.carc]
    denied_lines = [ln for ln in adjudicated_lines if ln.carc or ln.line_status == "denied"
                    or str(ln.line_no) in ((ln.encounter.appeal or {}).get("resolutions") or {})]
    adjudicated = [e for e in encounters if (e.adjudication or {}).get("outcome")]
    fpr = [e for e in adjudicated if e.submission_count == 1 and not (e.adjudication or {}).get("pended")
           and (e.adjudication or {}).get("outcome") == "paid"]
    closed = [e for e in encounters if e.stage == Stage.CLOSED]
    collected = sum(e.payer_paid + e.patient_paid for e in closed)
    collectible = 0.0
    for e in closed:
        res = (e.appeal or {}).get("resolutions") or {}
        for ln in e.lines:
            if ln.billing_decision == "do_not_perform":
                continue
            if res.get(str(ln.line_no), {}).get("resolution") == "write_off":
                collectible += ln.charge * ln.units * cat.PLANS[e.payer_id].allowed_ratio
            else:
                collectible += ln.charge * ln.units - ln.adjustment

    def pct(a: float, b: float) -> float | None:
        return round(100 * a / b, 1) if b else None

    return {
        "encounters": len(encounters),
        "closed": len(closed),
        "needs_attention": sum(1 for e in encounters if e.attention),
        "clean_claim_rate": pct(len(clean), len(submitted)),
        "denial_rate": pct(len(denied_lines), len(adjudicated_lines)),
        "days_to_cash": round(sum(e.sim_day for e in closed) / len(closed), 1) if closed else None,
        "net_collection_rate": pct(collected, collectible),
        "first_pass_resolution": pct(len(fpr), len(adjudicated)),
        "automated_steps": sum(e.automated_steps for e in encounters),
        "human_actions": sum(e.human_actions for e in encounters),
        "collected": round(collected, 2),
    }
