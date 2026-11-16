"""AI-assisted medical coding: scribe output -> ICD-10-CM diagnoses + CPT/HCPCS service lines.

Rules applied (each one is visible in the line rationale):
* specificity upgrades when the evidence supports them (sore throat + positive strep -> J02.0;
  diabetes + documented hyperglycemia -> E11.65) and laterality (right knee -> M17.11);
* signs and symptoms integral to a coded definitive diagnosis are not coded separately
  (fever with strep pharyngitis);
* E/M level from 2021 office-visit MDM: problems, data (tests ordered) and risk (prescription
  drug management) -- the level is the one met or exceeded by two of the three elements;
* preventive visits use age/new-patient codes (Medicare: annual wellness visit G0438/G0439) and a
  separately identifiable problem visit the same day gets modifier 25, as does an E/M billed
  with a minor procedure;
* RT/LT on lateral services, venipuncture once for blood labs, Medicare's own flu-shot admin
  code (G0008), and diagnosis pointers that prove medical necessity per line.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.pipeline import catalog as cat
from app.pipeline.scribe import Mention, ScribeResult

TEST_CATEGORIES = {"lab", "lab_poc", "imaging", "diagnostic"}
_KIND_ORDER = {"preventive": 0, "acute_complicated": 1, "acute": 2, "chronic": 2, "acute_minor": 3, "symptom": 4}
_MDM_NAMES = {1: "straightforward", 2: "low", 3: "moderate", 4: "high"}


@dataclass
class Necessity:
    supported: bool
    via: str | None = None
    missing: str | None = None


@dataclass
class CodingResult:
    diagnoses: list[dict] = field(default_factory=list)
    lines: list[dict] = field(default_factory=list)
    em: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def necessity(service: cat.Service, dx_codes: list[str], evidence: dict[str, str]) -> Necessity:
    """Does any diagnosis on the claim establish medical necessity for `service`?"""
    if not service.support and not service.support_with_evidence:
        return Necessity(True, "no diagnosis restriction")
    for dx in dx_codes:
        if any(dx.startswith(p) for p in service.support):
            return Necessity(True, dx)
    missing: list[str] = []
    for prefix, tags in service.support_with_evidence.items():
        for dx in dx_codes:
            if dx.startswith(prefix):
                lacking = [t for t in tags if t not in evidence]
                if not lacking:
                    return Necessity(True, f"{dx} + " + "; ".join(cat.EVIDENCE_LABELS[t] for t in tags))
                missing.append(f"{dx} needs: " + "; ".join(cat.EVIDENCE_LABELS[t].lower() for t in lacking))
    if missing:
        return Necessity(False, missing=" | ".join(missing))
    want = ", ".join(service.support[:6]) or "a qualifying diagnosis"
    return Necessity(False, missing=f"No diagnosis on the claim supports {service.code}; payers expect one of: {want}")


def _dx_from_mention(m: Mention, evidence: dict[str, str]) -> tuple[cat.Condition, str, str, float, str]:
    """(condition, code, description, confidence, rationale) after specificity and laterality."""
    cond = cat.CONDITION_BY_KEY[m.key]
    rationale = []
    for tag, upgraded in cond.replaced_by:
        if tag in evidence:
            cond = cat.CONDITION_BY_KEY[upgraded]
            rationale.append(f"Specificity: {cat.EVIDENCE_LABELS[tag].lower()}, coded {cond.code} instead of the unspecified code")
            break
    code, desc = cond.code, cond.description
    conf = 0.95 if m.speaker == "doctor" else 0.85
    if m.quote.startswith("Q:"):
        conf = 0.85
    if cond.lateral:
        if m.side and m.side in cond.lateral:
            code, desc = cond.lateral[m.side]
            rationale.append(f"Laterality: {m.side} side documented")
        else:
            conf = min(conf, 0.7)
            rationale.append("Laterality not documented: unspecified-side code used (review)")
    return cond, code, desc, conf, "; ".join(rationale)


def _service_line(code: str, *, desc: str | None = None, charge: float | None = None, system: str | None = None,
                  category: str | None = None, modifier: list[str] | None = None, dx: list[str] | None = None,
                  confidence: float = 0.95, evidence: str | None = None, rationale: str = "", source: str = "ai") -> dict:
    svc = cat.SERVICE_BY_CODE.get(code)
    return {
        "code": code,
        "code_system": system or (svc.system if svc else ("HCPCS" if code[0].isalpha() else "CPT")),
        "description": desc or (svc.description if svc else cat.EM_CODES[code][0]),
        "category": category or (svc.category if svc else "em"),
        "modifier": " ".join(modifier or []) or None,
        "units": 1,
        "dx_codes": dx or [],
        "charge": float(charge if charge is not None else (svc.charge if svc else cat.EM_CODES[code][1])),
        "confidence": confidence,
        "evidence": evidence,
        "rationale": rationale,
        "source": source,
    }


def _preventive_code(payer_id: str, new_patient: bool, age: int) -> str:
    if payer_id == "PYR-MCR":
        return "G0438" if new_patient else "G0439"
    bands = ((4, "99382", "99392"), (11, "99383", "99393"), (17, "99384", "99394"),
             (39, "99385", "99395"), (64, "99386", "99396"), (200, "99387", "99397"))
    for top, new, est in bands:
        if age <= top:
            return new if new_patient else est
    return "99397"


def _problem_level(problems: list[tuple[cat.Condition, str]], evidence: dict[str, str]) -> tuple[int, str]:
    worsening = any(t in evidence for t in ("worsening", "failed_conservative", "hyperglycemia"))
    chronic = [c for c, _ in problems if c.kind == "chronic"]
    if any(c.kind == "acute_complicated" for c, _ in problems):
        return 3, "acute illness with systemic symptoms or an undiagnosed new problem with uncertain prognosis"
    if chronic and worsening:
        return 3, "chronic illness with exacerbation, progression or not at treatment goal"
    if len(chronic) >= 2:
        return 3, "two or more stable chronic illnesses"
    if chronic:
        return 2, "one stable chronic illness"
    if any(c.kind in ("acute", "symptom") for c, _ in problems):
        return 2, "acute uncomplicated illness or injury"
    if len(problems) >= 2:
        return 2, "two or more self-limited or minor problems"
    return 1, "one self-limited or minor problem" if problems else "no problem addressed"


def _data_level(tests: list[str]) -> tuple[int, str]:
    n = len(tests)
    if n >= 3:
        return 3, f"{n} unique tests ordered/reviewed (category 1: three or more)"
    if n == 2:
        return 2, "2 unique tests ordered/reviewed (limited)"
    return 1, f"{n} unique test{'s' * (n != 1)} (minimal or none)"


def _risk_level(res: ScribeResult, minor_procedure: bool) -> tuple[int, str]:
    if res.rx:
        return 3, "prescription drug management (" + ", ".join(res.rx[:3]) + ")"
    if minor_procedure or res.otc:
        return 2, "over-the-counter drugs or minor procedure"
    return 1, "minimal risk"


def code_encounter(res: ScribeResult, *, payer_id: str, new_patient: bool, age: int) -> CodingResult:
    out = CodingResult()
    ev = res.evidence

    # ---- diagnoses
    chosen: dict[str, dict] = {}
    conds: dict[str, cat.Condition] = {}
    for m in sorted(res.conditions.values(), key=lambda x: x.position):
        cond, code, desc, conf, why = _dx_from_mention(m, ev)
        if code in chosen:
            if conf > chosen[code]["confidence"]:
                chosen[code].update(confidence=conf, evidence=m.quote)
            continue
        quote = m.quote
        for tag, _ in cat.CONDITION_BY_KEY[m.key].replaced_by:
            if tag in ev and cond.key != m.key:
                quote = f"{m.quote} | {ev[tag]}"
        chosen[code] = {"code": code, "description": desc, "confidence": conf, "evidence": quote,
                        "rationale": why or "Documented in the visit conversation", "kind": cond.kind}
        conds[code] = cond

    ordered = {c: m for c, m in res.orders.items() if m.status in ("ordered", "performed")}
    if "90686" in ordered and "Z23" not in chosen:
        z = cat.CONDITION_BY_KEY["immunization"]
        chosen["Z23"] = {"code": "Z23", "description": z.description, "confidence": 0.98, "evidence": ordered["90686"].quote,
                         "rationale": "Vaccine administered: immunization encounter code added", "kind": "preventive"}
        conds["Z23"] = z

    for code in list(chosen):
        cond = conds[code]
        if cond.integral_to:
            covering = [c for c in chosen if c != code and any(c.startswith(p) for p in cond.integral_to)]
            if covering:
                dropped = chosen.pop(code)
                conds.pop(code)
                out.warnings.append(f"{dropped['code']} {dropped['description']} not coded: integral to {covering[0]}")

    first_seen = {code: i for i, code in enumerate(chosen)}
    dx_list = sorted(chosen.values(), key=lambda d: (
        0 if d["code"].startswith("Z00") else (9 if d["code"] == "Z23" else 1 + _KIND_ORDER.get(d["kind"], 5)), first_seen[d["code"]]))
    for i, d in enumerate(dx_list):
        d["primary"] = i == 0
    out.diagnoses = dx_list
    dx_codes = [d["code"] for d in dx_list]
    problems = [(conds[d["code"]], d["code"]) for d in dx_list if conds[d["code"]].kind != "preventive"]
    problem_codes = [c for _, c in problems]

    # ---- services
    service_lines: list[dict] = []
    for code, m in ordered.items():
        svc = cat.SERVICE_BY_CODE[code]
        mods = []
        if svc.lateral_modifier:
            if m.side:
                mods.append("RT" if m.side == "right" else "LT")
        nec = necessity(svc, dx_codes, ev)
        pointers = _pointers(svc, dx_list, ev, nec)
        why = [f"Ordered by the clinician" if m.status == "ordered" else "Performed in the office (result documented)"]
        if svc.lateral_modifier:
            why.append(f"Modifier {mods[0]}: {m.side} side" if mods else "Side not documented: add RT/LT before submission")
        why.append(f"Medical necessity: supported by {nec.via}" if nec.supported else f"Medical necessity NOT established: {nec.missing}")
        service_lines.append(_service_line(code, modifier=mods, dx=pointers, confidence=0.95 if m.status == "ordered" else 0.9,
                                           evidence=m.quote, rationale=". ".join(why)) | {"necessity": nec.__dict__})

    blood = [ln for ln in service_lines if cat.SERVICE_BY_CODE[ln["code"]].blood_draw]
    if blood:
        service_lines.append(_service_line("36415", dx=blood[0]["dx_codes"][:4], confidence=0.98, source="rule",
                                           rationale="Venipuncture added once for the blood tests ordered")
                             | {"necessity": {"supported": True, "via": "blood draw for ordered labs", "missing": None}})
    if "90686" in ordered:
        admin = "G0008" if payer_id == "PYR-MCR" else "90471"
        service_lines.append(_service_line(admin, dx=["Z23"], confidence=0.98, source="rule",
                                           rationale="Vaccine administration" + (" (Medicare requires G0008 instead of 90471)" if admin == "G0008" else ""))
                             | {"necessity": {"supported": True, "via": "Z23", "missing": None}})

    # ---- E/M
    tests = [ln["code"] for ln in service_lines if ln["category"] in TEST_CATEGORIES and ln["code"] != "36415"]
    minor_proc = any(cat.SERVICE_BY_CODE[ln["code"]].global_procedure for ln in service_lines if ln["code"] in cat.SERVICE_BY_CODE)
    annual = any(d["code"].startswith("Z00") for d in dx_list)
    p_lvl, p_why = _problem_level(problems, ev)
    d_lvl, d_why = _data_level(tests)
    r_lvl, r_why = _risk_level(res, minor_proc)
    mdm = sorted([p_lvl, d_lvl, r_lvl])[1]
    em_lines: list[dict] = []
    em_info = {"problems": {"level": _MDM_NAMES[p_lvl], "why": p_why}, "data": {"level": _MDM_NAMES[d_lvl], "why": d_why},
               "risk": {"level": _MDM_NAMES[r_lvl], "why": r_why}, "mdm": _MDM_NAMES[mdm], "new_patient": new_patient}

    if annual:
        pcode = _preventive_code(payer_id, new_patient, age)
        z = [c for c in dx_codes if c.startswith("Z00")]
        em_lines.append(_service_line(pcode, dx=(z + problem_codes)[:4], confidence=0.9,
                                      evidence=chosen[z[0]]["evidence"],
                                      rationale=("Medicare does not cover routine physicals; coded as the annual wellness visit"
                                                 if pcode.startswith("G04") else f"Preventive visit for age {age}")
                                      + (", new patient" if new_patient else ", established patient"))
                        | {"necessity": {"supported": True, "via": "preventive benefit", "missing": None}})
        em_info["preventive_code"] = pcode
    separate_problem = bool(problems) and (bool(res.rx) or any(
        any(p in ln["dx_codes"] for p in problem_codes) for ln in service_lines if ln["category"] in TEST_CATEGORIES))
    if not annual or separate_problem:
        table = {1: "99202", 2: "99203", 3: "99204", 4: "99205"} if new_patient else {1: "99212", 2: "99213", 3: "99214", 4: "99215"}
        ecode = table[mdm]
        mods = ["25"] if (annual or minor_proc) else []
        why = f"MDM {_MDM_NAMES[mdm]} (2 of 3 elements): problems {_MDM_NAMES[p_lvl]}, data {_MDM_NAMES[d_lvl]}, risk {_MDM_NAMES[r_lvl]}"
        if annual:
            why += ". Modifier 25: significant, separately identifiable problem visit on the same day as the preventive visit"
        elif minor_proc:
            why += ". Modifier 25: separately identifiable E/M on the same day as a minor procedure"
        em_lines.append(_service_line(ecode, modifier=mods, dx=(problem_codes or dx_codes)[:4],
                                      confidence=0.85 if abs(p_lvl - d_lvl) + abs(d_lvl - r_lvl) <= 2 else 0.78,
                                      evidence=None, rationale=why)
                        | {"necessity": {"supported": True, "via": "problem-oriented visit", "missing": None}})
        em_info["code"] = ecode
    out.em = em_info
    out.lines = em_lines + service_lines
    if not dx_list:
        out.warnings.append("No diagnosis could be extracted from the conversation; add one before signing.")
    return out


def _pointers(svc: cat.Service, dx_list: list[dict], evidence: dict[str, str], nec: Necessity) -> list[str]:
    codes = [d["code"] for d in dx_list]
    if svc.category in ("vaccine", "vaccine_admin"):
        return ["Z23"]
    supporting = []
    for c in codes:
        if any(c.startswith(p) for p in svc.support):
            supporting.append(c)
        elif any(c.startswith(p) and all(t in evidence for t in tags) for p, tags in svc.support_with_evidence.items()):
            supporting.append(c)
    # Diagnostic tests point to the problem, not the wellness-exam Z code, whenever one supports them.
    non_z = [c for c in supporting if not c.startswith("Z00")]
    picked = non_z or supporting
    if not picked:
        picked = [c for c in codes if not c.startswith(("Z00", "Z23"))][:1] or codes[:1]
    return picked[:4]
