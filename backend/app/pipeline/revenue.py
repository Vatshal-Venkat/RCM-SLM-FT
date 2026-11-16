"""Back-end revenue cycle (slides 8-15): scrub, clearinghouse, adjudication, remittance, appeals.

Payer and clearinghouse behaviour is simulated deterministically from the encounter ID so a demo
run is repeatable: about one in five first submissions bounces at the payer front door (277CA)
and is auto-corrected; some high-dollar claims are pended for records. Denials are never random:
a line is denied only for a reason the coverage engine already flagged (no authorization,
medical necessity not established).
"""

from __future__ import annotations

from datetime import date, timedelta

from app.models.encounter import Encounter, EncounterLine
from app.pipeline import catalog as cat
from app.pipeline.coding import necessity
from app.pipeline.coverage import stable_fraction

BILLABLE = ("bill_insurance", "bill_with_abn")


def billed_lines(enc: Encounter) -> list[EncounterLine]:
    return [ln for ln in enc.lines if ln.billing_decision in BILLABLE]


def _mods(ln: EncounterLine) -> list[str]:
    return (ln.modifier or "").split()


def _set_mods(ln: EncounterLine, mods: list[str]) -> None:
    ln.modifier = " ".join(dict.fromkeys(m for m in mods if m)) or None


def valid_dx_codes() -> set[str]:
    out = set()
    for c in cat.CONDITIONS:
        out.add(c.code)
        for code, _ in (c.lateral or {}).values():
            out.add(code)
    return out


# --------------------------------------------------------------------------- scrubber (slide 8)


def scrub(enc: Encounter, evidence: dict[str, str]) -> dict:
    """Run the scrubber checks, auto-fixing what can be fixed safely. Returns the scrub report."""
    lines = billed_lines(enc)
    dx = [d["code"] for d in (enc.coding or {}).get("diagnoses", [])]
    doctor = cat.DOCTOR_BY_ID[enc.doctor_id]
    checks: list[dict] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"check": name, "status": status, "detail": detail})

    # 1. Missing or invalid fields
    missing = []
    if not enc.member_id:
        missing.append("subscriber ID")
    if not dx:
        missing.append("diagnosis")
    missing += [f"diagnosis pointer on {ln.code}" for ln in lines if not ln.dx_codes]
    add("Missing or invalid fields", "fail" if missing else "pass",
        ("Missing: " + ", ".join(missing)) if missing else
        f"Subscriber {enc.member_id}, rendering NPI {doctor.npi}, billing TIN {cat.PROVIDER_TAX_ID[enc.provider_id]}, "
        f"date of service {enc.scheduled_at.date()}, {len(dx)} diagnosis code(s), place of service "
        f"{'22' if cat.claim_form(enc.provider_id)[0] == 'UB-04' else '11'}.")

    # 2. Valid, current codes
    known_dx = valid_dx_codes()
    bad = [c for c in dx if c not in known_dx] + [ln.code for ln in lines if ln.code not in cat.SERVICE_BY_CODE and ln.code not in cat.EM_CODES]
    add("Valid, current codes", "fail" if bad else "pass",
        f"Unknown or retired code(s): {', '.join(bad)}" if bad else
        f"All {len(dx)} ICD-10-CM and {len(lines)} CPT/HCPCS codes are valid for {enc.scheduled_at.year}.")

    # 3. Diagnosis supports procedure
    risky = []
    for ln in lines:
        svc = cat.SERVICE_BY_CODE.get(ln.code)
        if svc and not necessity(svc, ln.dx_codes or [], evidence).supported and ln.billing_decision == "bill_insurance":
            risky.append(ln.code)
    abn = [ln.code for ln in lines if ln.billing_decision == "bill_with_abn"]
    if risky:
        add("Diagnosis supports procedure", "warn", f"Medical necessity not established for {', '.join(risky)}; denial likely.")
    else:
        add("Diagnosis supports procedure", "pass", "Every line points to a diagnosis that supports it"
            + (f"; {', '.join(abn)} billed with a signed ABN (modifier GA)." if abn else "."))

    # 4. NCCI bundling edits
    codes = {ln.code for ln in lines}
    fixes = []
    for col1, col2, note in cat.NCCI_EDITS:
        if col1 in codes and col2 in codes:
            for ln in lines:
                if ln.code == col2:
                    ln.billing_decision, ln.line_status = "do_not_perform", "not_performed"
            fixes.append(f"removed {col2} ({note})")
    em = [ln for ln in lines if ln.code in cat.EM_CODES and not ln.code.startswith(("G04", "9938", "9939"))]
    proc = [ln for ln in lines if (s := cat.SERVICE_BY_CODE.get(ln.code)) and s.global_procedure]
    preventive = [ln for ln in lines if ln.code.startswith(("G04", "9938", "9939"))]
    for ln in em:
        if (proc or preventive) and "25" not in _mods(ln):
            _set_mods(ln, ["25", *_mods(ln)])
            fixes.append(f"added modifier 25 to {ln.code}")
    add("NCCI bundling edits", "fixed" if fixes else "pass",
        ("Auto-corrected: " + "; ".join(fixes)) if fixes else "No column 1 / column 2 conflicts; modifier 25 present where required.")

    # 5. Payer-specific rules
    notes, fails = [], []
    medicare = enc.payer_id == "PYR-MCR"
    for ln in lines:
        if medicare and ln.code == "90471":
            ln.code, ln.description = "G0008", cat.SERVICE_BY_CODE["G0008"].description
            notes.append("Medicare flu vaccine admin: 90471 -> G0008")
        if medicare and ln.code.startswith(("9938", "9939")):
            ln.code, ln.description, ln.charge = "G0439", cat.EM_CODES["G0439"][0], cat.EM_CODES["G0439"][1]
            notes.append("Medicare routine physical -> annual wellness visit G0439")
        if ln.coverage_status == "prior_auth_required" and not ln.auth_number:
            fails.append(f"{ln.code} needs an authorization number")
        if ln.billing_decision == "bill_with_abn" and "GA" not in _mods(ln):
            _set_mods(ln, [*_mods(ln), "GA"])
            notes.append(f"modifier GA (ABN on file) on {ln.code}")
        svc = cat.SERVICE_BY_CODE.get(ln.code)
        if svc and svc.lateral_modifier and not ({"RT", "LT"} & set(_mods(ln))):
            notes.append(f"{ln.code} has no RT/LT modifier (side not documented)")
    if enc.payer_id == "PYR-MCD" and not doctor.primary_care:
        notes.append("Medicaid specialist visit: referring PCP added from registration")
    tf = cat.PAYER_INFO[enc.payer_id]["timely_filing_days"]
    notes.append(f"timely filing: day 1 of {tf}")
    auths = [f"{ln.code} auth {ln.auth_number}" for ln in lines if ln.auth_number]
    if auths:
        notes.append("authorizations on claim: " + ", ".join(auths))
    add("Payer-specific rules", "fail" if fails else ("fixed" if any("->" in n or "GA" in n for n in notes) else "pass"),
        "; ".join(fails + notes))

    clean = not any(c["status"] == "fail" for c in checks)
    form, txn = cat.claim_form(enc.provider_id)
    return {"clean": clean, "checks": checks, "claim_form": form, "transaction": txn,
            "auto_fixes": sum(c["status"] == "fixed" for c in checks),
            "billed_lines": len(billed_lines(enc)), "total_billed": round(sum(ln.charge * ln.units for ln in billed_lines(enc)), 2)}


# --------------------------------------------------------------------------- X12 previews


def build_837(enc: Encounter, claim_ref: str) -> str:
    """Simplified 837P/837I preview (segment structure only; not a submittable file)."""
    doctor = cat.DOCTOR_BY_ID[enc.doctor_id]
    form, txn = cat.claim_form(enc.provider_id)
    lines = billed_lines(enc)
    dx = [d["code"].replace(".", "") for d in (enc.coding or {}).get("diagnoses", [])][:12]
    total = sum(ln.charge * ln.units for ln in lines)
    pos = "22" if form == "UB-04" else "11"
    first, *rest = enc.patient_name.split(" ", 1) + [""]
    last = rest[0] or first
    seg = [
        f"ST*{txn[:3]}*0001*005010X222A1~",
        f"BHT*0019*00*{claim_ref}*{enc.scheduled_at:%Y%m%d}*1200*CH~",
        f"NM1*85*2*{cat.PROVIDER_INFO[enc.provider_id]['name'].upper()}*****XX*{doctor.npi}~",
        f"REF*EI*{cat.PROVIDER_TAX_ID[enc.provider_id].replace('-', '')}~",
        f"NM1*IL*1*{last.upper()}*{first.upper()}****MI*{enc.member_id}~",
        f"NM1*PR*2*{cat.PAYER_INFO[enc.payer_id]['name'].upper()}*****PI*{enc.payer_id}~",
        f"CLM*{claim_ref}*{total:.2f}***{pos}:B:1*Y*A*Y*Y~",
        "HI*" + "*".join(("ABK:" if i == 0 else "ABF:") + c for i, c in enumerate(dx)) + "~",
        f"NM1*82*1*{doctor.name.replace('Dr. ', '').split()[-1].upper()}*****XX*{doctor.npi}~",
    ]
    for ln in lines:
        if ln.auth_number:
            seg.append(f"REF*G1*{ln.auth_number}~")
    for i, ln in enumerate(lines, 1):
        ptrs = ":".join(str(dx.index(c.replace(".", "")) + 1) for c in (ln.dx_codes or []) if c.replace(".", "") in dx) or "1"
        mods = ":".join(_mods(ln))
        seg += [f"LX*{i}~", f"SV1*HC:{ln.code}{':' + mods if mods else ''}*{ln.charge * ln.units:.2f}*UN*{ln.units}***{ptrs}~",
                f"DTP*472*D8*{enc.scheduled_at:%Y%m%d}~"]
    seg.append(f"SE*{len(seg) + 1}*0001~")
    return "\n".join(seg)


# --------------------------------------------------------------------------- clearinghouse (slide 9)


def clearinghouse_submit(enc: Encounter, attempt: int) -> dict:
    """999 (file received) + 277CA (claim accepted or rejected) for one submission."""
    claim_ref = f"{enc.id}-{attempt}"
    reject = attempt == 1 and stable_fraction(enc.id, "277ca") < 0.2
    sub = {
        "attempt": attempt, "claim_ref": claim_ref, "clearinghouse": "Synthetic Clearinghouse (Availity-style)",
        "steps": [
            {"step": "Translate", "status": "pass", "detail": f"Converted to HIPAA X12 {cat.claim_form(enc.provider_id)[1]} (005010)."},
            {"step": "Validate", "status": "pass", "detail": "Clearinghouse edits passed (format, code sets, NPI checksum)."},
            {"step": "Route", "status": "pass", "detail": f"Routed to {cat.PAYER_INFO[enc.payer_id]['name']} (payer ID {enc.payer_id})."},
        ],
        "ack_999": {"status": "A", "detail": "Implementation acknowledgment: file accepted"},
        "x12_837": build_837(enc, claim_ref),
    }
    if reject:
        code, reason, fix = cat.REJECTION_SCENARIOS[int(stable_fraction(enc.id, "why") * len(cat.REJECTION_SCENARIOS))]
        sub["ack_277ca"] = {"status": "rejected", "category_code": code, "detail": reason, "auto_fix": fix}
        sub["steps"].append({"step": "Acknowledge", "status": "fail", "detail": f"277CA rejected ({code}): {reason}"})
    else:
        icn = f"{int(stable_fraction(enc.id, str(attempt), 'icn') * 1e13):013d}"
        sub["ack_277ca"] = {"status": "accepted", "category_code": "A2:20", "detail": "Accepted for adjudication", "payer_icn": icn}
        sub["steps"].append({"step": "Acknowledge", "status": "pass", "detail": f"277CA accepted; payer claim number {icn}."})
    return sub


# --------------------------------------------------------------------------- adjudication (slide 10)


def should_pend(enc: Encounter) -> bool:
    total = sum(ln.charge * ln.units for ln in billed_lines(enc))
    return total >= 1000 and stable_fraction(enc.id, "pend") < 0.5 and not (enc.adjudication or {}).get("records_sent")


def adjudicate(enc: Encounter, evidence: dict[str, str]) -> dict:
    """Five gates per claim; line-level outcomes are written onto the lines."""
    lines = billed_lines(enc)
    elig = enc.eligibility or {}
    gates = [
        {"gate": "Front-end edits", "status": "pass", "detail": "Claim complete and valid (accepted by 277CA)."},
        {"gate": "Eligibility", "status": "pass" if elig.get("active") else "fail",
         "detail": f"Member active on {enc.scheduled_at.date()} ({elig.get('plan_name', 'plan')})."},
    ]
    auth_fail = [ln for ln in lines if ln.coverage_status == "prior_auth_required" and ln.auth_status != "approved"]
    auth_lines = [ln for ln in lines if ln.coverage_status == "prior_auth_required"]
    gates.append({"gate": "Prior authorization", "status": "fail" if auth_fail else "pass",
                  "detail": ("No approval on file for " + ", ".join(ln.code for ln in auth_fail)) if auth_fail else
                  (f"Approval on file: {', '.join(f'{ln.code} ({ln.auth_number})' for ln in auth_lines)}" if auth_lines
                   else "No service on this claim requires authorization.")})
    nec_fail = []
    for ln in lines:
        svc = cat.SERVICE_BY_CODE.get(ln.code)
        if svc and not necessity(svc, ln.dx_codes or [], evidence).supported:
            nec_fail.append(ln)
    gates.append({"gate": "Medical necessity", "status": "fail" if nec_fail else "pass",
                  "detail": ("Diagnosis does not justify " + ", ".join(ln.code for ln in nec_fail)) if nec_fail
                  else "Every service is justified by a diagnosis on the claim."})
    gates.append({"gate": "Pricing", "status": "pass",
                  "detail": f"Priced at the contracted rate ({round(cat.PLANS[enc.payer_id].allowed_ratio * 100)}% of billed charges)."})

    denied = {ln.id for ln in auth_fail} | {ln.id for ln in nec_fail}
    for ln in lines:
        if ln.id in denied:
            ln.line_status = "denied"
            if ln in auth_fail:
                ln.carc = "CO-197"
            else:
                ln.carc = "PR-50" if "GA" in _mods(ln) else "CO-50"
        else:
            ln.line_status = "paid"
    paid = [ln for ln in lines if ln.line_status == "paid"]
    outcome = "paid" if not denied else ("denied" if not paid else "partially_paid")
    return {"outcome": outcome, "gates": gates, "denied_lines": [ln.code for ln in lines if ln.id in denied],
            "paid_lines": [ln.code for ln in paid]}


# --------------------------------------------------------------------------- remittance (slide 14)

CARC_TEXT = {
    "CO-45": "Charge exceeds fee schedule/maximum allowable (contractual adjustment)",
    "PR-1": "Deductible amount",
    "PR-2": "Coinsurance amount",
    "PR-3": "Co-payment amount",
    "CO-50": "Non-covered: not deemed a medical necessity by the payer (provider liability)",
    "PR-50": "Non-covered: not deemed a medical necessity; patient liable under signed ABN",
    "CO-197": "Precertification/authorization absent",
}


def build_era(enc: Encounter, lines: list[EncounterLine], pay_date: date, kind: str = "original") -> dict:
    """835 ERA + EFT for the given lines (amounts already set on the lines)."""
    era_lines, total_paid = [], 0.0
    for ln in lines:
        adj = []
        billed = round(ln.charge * ln.units, 2)
        if ln.line_status == "denied":
            adj.append({"code": ln.carc, "amount": billed if ln.carc != "PR-50" else round(billed - ln.allowed, 2), "text": CARC_TEXT[ln.carc]})
            if ln.carc == "PR-50":
                adj = [{"code": "CO-45", "amount": round(billed - ln.allowed, 2), "text": CARC_TEXT["CO-45"]},
                       {"code": "PR-50", "amount": ln.allowed, "text": CARC_TEXT["PR-50"]}]
        else:
            if billed - ln.allowed > 0.004:
                adj.append({"code": "CO-45", "amount": round(billed - ln.allowed, 2), "text": CARC_TEXT["CO-45"]})
            cs = (ln.encounter.coding or {}).get("cost_share", {}).get(str(ln.line_no), {})
            for key, code in (("deductible", "PR-1"), ("coinsurance", "PR-2"), ("copay", "PR-3")):
                if cs.get(key, 0) > 0.004:
                    adj.append({"code": code, "amount": cs[key], "text": CARC_TEXT[code]})
        total_paid += ln.payer_paid
        era_lines.append({"line_no": ln.line_no, "code": ln.code, "modifier": ln.modifier, "billed": billed,
                          "allowed": ln.allowed, "paid": ln.payer_paid, "patient_resp": ln.patient_resp,
                          "status": ln.line_status, "adjustments": adj})
    trace = f"EFT{int(stable_fraction(enc.id, kind, 'trn') * 1e10):010d}"
    total_paid = round(total_paid, 2)
    seg = [f"ST*835*0001~", f"BPR*I*{total_paid:.2f}*C*ACH*CCP*01*999999999*DA*123456*{pay_date:%Y%m%d}~",
           f"TRN*1*{trace}*1{enc.payer_id[-3:]}~", f"CLP*{enc.id}*{'1' if total_paid else '4'}*"
           f"{sum(x['billed'] for x in era_lines):.2f}*{total_paid:.2f}*{sum(x['patient_resp'] for x in era_lines):.2f}*12~"]
    for x in era_lines:
        seg.append(f"SVC*HC:{x['code']}*{x['billed']:.2f}*{x['paid']:.2f}~")
        for a in x["adjustments"]:
            g, r = a["code"].split("-")
            seg.append(f"CAS*{g}*{r}*{a['amount']:.2f}~")
    seg.append(f"SE*{len(seg) + 1}*0001~")
    return {"kind": kind, "payment_date": pay_date.isoformat(), "eft_trace": trace,
            "method": "EFT (ACH CCD+)" if total_paid > 0 else "no payment (ERA only)",
            "total_paid": total_paid, "lines": era_lines, "x12_835": "\n".join(seg)}


# --------------------------------------------------------------------------- appeals (slide 13)


def appeal_assessment(ln: EncounterLine, evidence: dict[str, str]) -> dict:
    """Should we appeal? Only when the documentation contains something the payer did not weigh."""
    svc = cat.SERVICE_BY_CODE.get(ln.code)
    relevant = set()
    if svc:
        for tags in svc.support_with_evidence.values():
            relevant |= set(tags)
    found = [t for t in relevant if t in evidence]
    if ln.carc == "PR-50":
        return {"recommend": False, "likelihood": "low", "found": found,
                "reason": "Signed ABN on file and no new clinical evidence: the patient is responsible. An appeal would not succeed."}
    if found:
        return {"recommend": True, "likelihood": "moderate", "found": found,
                "reason": "The note documents " + "; ".join(cat.EVIDENCE_LABELS[t].lower() for t in found) + " that supports necessity."}
    return {"recommend": True, "likelihood": "low", "found": [],
            "reason": "Provider liability (CO): the balance cannot be billed to the patient, so an appeal is the only recovery path; "
                      "documentation is thin, so success is unlikely."}


def draft_appeal(enc: Encounter, ln: EncounterLine, evidence: dict[str, str], assessment: dict) -> str:
    doctor = cat.DOCTOR_BY_ID[enc.doctor_id]
    payer = cat.PAYER_INFO[enc.payer_id]["name"]
    icn = next((s["ack_277ca"].get("payer_icn") for s in reversed(enc.clearinghouse or []) if s["ack_277ca"]["status"] == "accepted"), "")
    dx = ", ".join(f"{d['code']} ({d['description']})" for d in (enc.coding or {}).get("diagnoses", []))
    quotes = "\n".join(f'  - "{evidence[t]}"' for t in assessment["found"]) or "  - (see enclosed visit note)"
    return (
        f"To: {payer}, Appeals / Reconsideration Unit\n"
        f"Re: Request for reconsideration of denied service\n"
        f"Claim: {enc.id}   Payer claim number: {icn}   Member ID: {enc.member_id}\n"
        f"Date of service: {enc.scheduled_at:%B %d, %Y}   Service: {ln.code} {ln.description}\n"
        f"Denial: {ln.carc} {CARC_TEXT.get(ln.carc, '')}\n\n"
        f"We request reconsideration of the denial above. The service was ordered by {doctor.name} ({doctor.specialty}, "
        f"NPI {doctor.npi}) for: {dx}.\n\n"
        f"The visit documentation records the following findings supporting medical necessity:\n{quotes}\n\n"
        f"The enclosed clinical note shows the service was reasonable and necessary for the patient's condition. "
        f"Please reprocess the line for payment.\n\nEnclosures: visit note, order, prior authorization record (if any).\n"
        f"Sincerely,\nRevenue Cycle Team, {cat.PROVIDER_INFO[enc.provider_id]['name']}"
    )


def appeal_outcome(assessment: dict) -> str:
    return "overturned" if assessment["likelihood"] in ("moderate", "high") else "upheld"


# --------------------------------------------------------------------------- patient statement (slide 15)


def build_statement(enc: Encounter, statement_date: date) -> dict:
    items = []
    for ln in enc.lines:
        if ln.patient_resp > 0.004:
            why = {"self_pay": "Self-pay (not covered by your plan)", "denied": "Not paid by insurance (ABN signed)"}.get(
                ln.line_status, "Your share (copay / deductible / coinsurance)")
            items.append({"code": ln.code, "description": ln.description, "amount": ln.patient_resp, "why": why})
    owed = round(sum(i["amount"] for i in items), 2)
    paid = round(enc.patient_paid, 2)
    return {"statement_date": statement_date.isoformat(), "due_date": (statement_date + timedelta(days=30)).isoformat(),
            "items": items, "total_patient_responsibility": owed, "paid_to_date": paid,
            "balance_due": round(max(owed - paid, 0), 2), "credit": round(max(paid - owed, 0), 2),
            "payment_options": ["Pay online in the patient portal", "Payment plan (3 or 6 months, no interest)", "Card on file"],
            "portal": cat.PATIENT_PORTAL_URL, "aging_bucket": "0-30 days"}
