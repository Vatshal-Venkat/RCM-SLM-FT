"""Front-end checks and coverage intelligence (slides 5, 10, 12).

* `verify_eligibility`  simulated X12 270/271: plan active?, copay, deductible remaining, coinsurance
* `determine_coverage`  per service line, before the claim goes out:
      covered | prior_auth_required | not_covered | medical_necessity_risk
  plus the default billing decision (bill insurance, bill with an ABN, patient self-pay, or do not
  perform) so the doctor and patient know what insurance will and will not pay *before* the test.
* `price_lines`         contract allowed amount and patient cost share per line (copay /
                        deductible / coinsurance) -- the same maths the payer simulator uses, so
                        estimates and the final remittance agree unless the payer denies a line.
* `request_authorizations`  simulated X12 278 for lines that need prior authorization.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date

from app.pipeline import catalog as cat
from app.pipeline.coding import necessity

PREVENTIVE_CODES = {"G0438", "G0439"} | {c for c in cat.EM_CODES if c.startswith(("9938", "9939"))}
EM_PROBLEM_CODES = {c for c in cat.EM_CODES if c.startswith(("9920", "9921"))}


def stable_fraction(*parts: str) -> float:
    """Deterministic pseudo-random number in [0, 1) from text (simulated payer behaviour)."""
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(h[:8], 16) / 0x1_0000_0000


def _r2(x: float) -> float:
    return round(x + 1e-9, 2)


# --------------------------------------------------------------------------- eligibility (270/271)


def verify_eligibility(payer_id: str, member_id: str, service_date: date, specialist: bool) -> dict:
    plan = cat.PLANS[payer_id]
    payer = cat.PAYER_INFO[payer_id]
    trace = f"270-{hashlib.sha1(f'{payer_id}{member_id}{service_date}'.encode()).hexdigest()[:10].upper()}"
    base = {"transaction": "270/271", "trace_number": trace, "payer_id": payer_id, "payer": payer["name"],
            "payer_type": payer["payer_type"], "member_id": member_id, "service_date": service_date.isoformat()}
    if not re.match(plan.member_id_pattern, member_id.upper()):
        return base | {"active": False, "error_code": "AAA*72", "error": "Invalid/missing subscriber ID",
                       "message": f"Member ID does not match the {plan.plan_name} format (example: {plan.member_id_example}). "
                                  "Re-check the insurance card and re-verify."}
    if member_id.endswith("0000"):
        return base | {"active": False, "error_code": "EB*6", "error": "Coverage inactive",
                       "message": f"Coverage terminated before {service_date.isoformat()}. Ask the patient for current insurance "
                                  "or set up self-pay before the visit."}
    met = _r2(plan.deductible * round(stable_fraction(member_id, "ded"), 2))
    copay = plan.copay_specialist if specialist else plan.copay_pcp
    return base | {
        "active": True, "plan_name": plan.plan_name, "coverage_start": f"{service_date.year}-01-01",
        "copay": copay, "copay_type": "specialist" if specialist else "primary care",
        "deductible": plan.deductible, "deductible_met": met, "deductible_remaining": _r2(plan.deductible - met),
        "coinsurance_pct": round(plan.coinsurance * 100), "oop_max": plan.oop_max,
        "message": "Coverage active on the date of service.",
    }


def planned_service_auth(visit_reason: str, payer_id: str) -> dict:
    """Step 4 at booking: does a service named in the visit reason need prior authorization?"""
    found = []
    for svc in cat.SERVICES:
        for p in svc.phrases:
            if re.search(rf"(?<![\w-]){p}(?![\w-])", visit_reason, re.I):
                found.append(svc)
                break
    needs = [s for s in found if payer_id in s.auth_payers]
    if needs:
        return {"required": True, "services": [f"{s.code} {s.description}" for s in needs],
                "message": "Planned service needs prior authorization; it will be requested as soon as the doctor orders it."}
    return {"required": False, "services": [],
            "message": "An office visit does not need prior authorization. Tests ordered during the visit are checked automatically."}


# --------------------------------------------------------------------------- coverage


def determine_coverage(line: dict, payer_id: str, dx_codes: list[str], evidence: dict[str, str]) -> dict:
    """Coverage status, reason and default billing decision for one line."""
    code = line["code"]
    medicare = payer_id == "PYR-MCR"
    if code in cat.EM_CODES:
        if medicare and code.startswith(("9938", "9939")):
            return {"coverage_status": "not_covered", "billing_decision": "self_pay",
                    "coverage_reason": "Medicare does not cover routine physical exams; bill the annual wellness visit (G0439) instead."}
        why = "Preventive benefit: covered with no cost share" if code in PREVENTIVE_CODES else "Office visit covered under the plan's benefits"
        return {"coverage_status": "covered", "billing_decision": "bill_insurance", "coverage_reason": why}
    svc = cat.SERVICE_BY_CODE.get(code)
    if svc is None:
        return {"coverage_status": "medical_necessity_risk", "billing_decision": "bill_insurance",
                "coverage_reason": "Code is not in the payer policy reference; verify coverage manually."}
    nec = necessity(svc, dx_codes, evidence)
    if not nec.supported and svc.unsupported == "not_covered":
        return {"coverage_status": "not_covered", "billing_decision": "self_pay",
                "coverage_reason": (svc.not_covered_reason or "Not a covered benefit for this diagnosis.")
                + " Offer the patient the self-pay price, or skip the test."}
    if payer_id in svc.auth_payers:
        return {"coverage_status": "prior_auth_required", "billing_decision": "bill_insurance",
                "coverage_reason": f"{cat.PAYER_INFO[payer_id]['name']} requires prior authorization for {svc.code}. "
                + (f"Criteria met: {nec.via}." if nec.supported else f"Criteria at risk: {nec.missing}.")}
    if not nec.supported:
        if medicare:
            return {"coverage_status": "medical_necessity_risk", "billing_decision": "bill_with_abn",
                    "coverage_reason": f"Likely denied as not medically necessary ({nec.missing}). Have the patient sign an "
                                       "Advance Beneficiary Notice (ABN) before the service; the claim line carries modifier GA so "
                                       "the patient, not the practice, is responsible if Medicare denies it."}
        return {"coverage_status": "medical_necessity_risk", "billing_decision": "bill_insurance",
                "coverage_reason": f"Payer may deny as not medically necessary ({nec.missing}). Strengthen documentation or discuss cost with the patient."}
    return {"coverage_status": "covered", "billing_decision": "bill_insurance",
            "coverage_reason": f"Covered: medical necessity supported by {nec.via}."}


def request_authorizations(lines: list[dict], payer_id: str, dx_codes: list[str], evidence: dict[str, str], encounter_id: str) -> list[dict]:
    """Simulated real-time X12 278: approve when the documented criteria are met, otherwise deny."""
    results = []
    for ln in lines:
        if ln.get("coverage_status") != "prior_auth_required":
            continue
        svc = cat.SERVICE_BY_CODE[ln["code"]]
        nec = necessity(svc, dx_codes, evidence)
        if nec.supported:
            num = f"PA{int(stable_fraction(encounter_id, ln['code']) * 1e8):08d}"
            ln.update(auth_status="approved", auth_number=num, billing_decision="bill_insurance")
            results.append({"code": ln["code"], "status": "approved", "auth_number": num,
                            "detail": f"Approved: {nec.via}. Valid 60 days."})
        else:
            ln.update(auth_status="denied", auth_number=None, billing_decision="do_not_perform")
            results.append({"code": ln["code"], "status": "denied", "auth_number": None,
                            "detail": f"Denied: medical necessity criteria not met ({nec.missing}). "
                                      "The test should not be scheduled unless the patient chooses to self-pay or new findings are documented."})
    return results


# --------------------------------------------------------------------------- pricing / cost share


def price_lines(lines: list[dict], payer_id: str, eligibility: dict | None) -> dict:
    """Fill allowed / est_payer / est_patient on each line, applying copay, deductible and coinsurance in order."""
    plan = cat.PLANS[payer_id]
    ptype = cat.PAYER_INFO[payer_id]["payer_type"]
    ded_left = float((eligibility or {}).get("deductible_remaining", plan.deductible))
    copay = float((eligibility or {}).get("copay", plan.copay_pcp))
    copay_used = False
    totals = {"charge": 0.0, "allowed": 0.0, "payer": 0.0, "patient": 0.0, "deductible_applied": 0.0, "copay": 0.0, "coinsurance": 0.0}

    for ln in lines:
        charge = float(ln["charge"]) * int(ln.get("units", 1) or 1)
        decision = ln.get("billing_decision", "bill_insurance")
        allowed = _r2(charge * plan.allowed_ratio)
        share = {"deductible": 0.0, "copay": 0.0, "coinsurance": 0.0}
        if decision == "do_not_perform":
            ln.update(allowed=0.0, est_payer=0.0, est_patient=0.0, cost_share=share)
            continue
        totals["charge"] += charge
        if decision == "self_pay":
            pay = _r2(charge * cat.SELF_PAY_DISCOUNT)
            ln.update(allowed=0.0, est_payer=0.0, est_patient=pay, cost_share=share | {"self_pay": pay})
            totals["patient"] += pay
            continue
        if decision == "bill_with_abn":
            # Expected to be denied; with a signed ABN the patient owes the Medicare allowed amount.
            ln.update(allowed=allowed, est_payer=0.0, est_patient=allowed, cost_share=share | {"abn_liability": allowed})
            totals["allowed"] += allowed
            totals["patient"] += allowed
            continue

        code, category = ln["code"], ln.get("category", "")
        patient = 0.0
        no_cost_share = (code in PREVENTIVE_CODES or category in ("vaccine", "vaccine_admin") or ptype == "medicaid"
                         or (ptype == "medicare" and category in ("lab", "lab_poc")))
        if not no_cost_share:
            if code in EM_PROBLEM_CODES and ptype in ("commercial", "medicare_advantage") and copay > 0 and not copay_used:
                share["copay"] = min(copay, allowed)
                copay_used = True
            else:
                d = min(ded_left, allowed)
                ded_left -= d
                share["deductible"] = _r2(d)
                share["coinsurance"] = _r2((allowed - d) * plan.coinsurance)
            patient = _r2(share["copay"] + share["deductible"] + share["coinsurance"])
        ln.update(allowed=allowed, est_payer=_r2(allowed - patient), est_patient=patient, cost_share=share)
        totals["allowed"] += allowed
        totals["payer"] += allowed - patient
        totals["patient"] += patient
        totals["deductible_applied"] += share["deductible"]
        totals["copay"] += share["copay"]
        totals["coinsurance"] += share["coinsurance"]
    return {k: _r2(v) for k, v in totals.items()}
