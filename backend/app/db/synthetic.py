"""Deterministic synthetic RCM claims generator.

Produces realistic, fully synthetic professional/institutional claims with payments, denials
(CARC-coded), rejections, appeals and status history. No real PHI: patients are opaque IDs with a
birth year, sex and state; all payer and provider organisations are fictional.

Embedded scenarios (documented in `dataset_metadata`) give the analytics and Copilot real
patterns to discover:
  S1  Cobalt Mutual Insurance adds prior-authorization requirements on 2026-05-01 that front-end
      staff miss -> CARC 197 denials spike and the overall denial rate rises from May 2026.
  S2  Cobalt Mutual Insurance slows adjudication from 2026-07-01 (~48 vs ~24 days) -> pending
      claims and AR grow.
  S3  Lakeside Dermatology has persistent modifier/bundling errors (CARC 4, 97) -> highest
      provider denial rate.
  S4  State Medicaid has higher front-end rejection rates (member ID / eligibility).
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from datetime import date, timedelta

# ----------------------------------------------------------------------------- reference data
PAYERS = [
    # id, name, type, share, base_denial, adjudication_days(mean, sd), allowed_ratio(lo, hi), timely_filing_days
    ("PYR-MCR", "Medicare Part B (Synthetic)", "medicare", 0.28, 0.05, (16, 4), (0.42, 0.52), 365),
    ("PYR-MCD", "State Medicaid (Synthetic)", "medicaid", 0.13, 0.08, (34, 8), (0.33, 0.42), 180),
    ("PYR-NWH", "Northwind Health Plan", "commercial", 0.19, 0.055, (21, 5), (0.58, 0.70), 180),
    ("PYR-COB", "Cobalt Mutual Insurance", "commercial", 0.15, 0.06, (24, 6), (0.60, 0.72), 90),
    ("PYR-LSH", "Lakeshore Health Partners", "medicare_advantage", 0.15, 0.075, (28, 7), (0.48, 0.58), 365),
    ("PYR-STC", "Sterling Care Assurance", "commercial", 0.10, 0.04, (18, 4), (0.64, 0.76), 120),
]

PROVIDERS = [
    # id, name, specialty, type, state, volume_weight, denial_multiplier
    ("PRV-01", "Riverside Family Medicine", "Family Medicine", "professional", "OH", 0.20, 0.9),
    ("PRV-02", "Summit Orthopedics", "Orthopedic Surgery", "professional", "OH", 0.12, 1.1),
    ("PRV-03", "Harborview Cardiology", "Cardiology", "professional", "PA", 0.12, 1.0),
    ("PRV-04", "Clearwater Imaging Center", "Diagnostic Radiology", "facility", "PA", 0.13, 1.0),
    ("PRV-05", "Maple Grove Pediatrics", "Pediatrics", "professional", "OH", 0.12, 0.8),
    ("PRV-06", "Northgate Physical Therapy", "Physical Therapy", "professional", "MI", 0.11, 1.0),
    ("PRV-07", "Lakeside Dermatology", "Dermatology", "professional", "MI", 0.10, 1.0),
    ("PRV-08", "Valley Behavioral Health", "Behavioral Health", "professional", "PA", 0.10, 1.05),
]

# cpt, description, base charge, weight, requires_auth (commercial/MA/Medicaid)
PROCEDURES: dict[str, list[tuple[str, str, float, float, bool]]] = {
    "PRV-01": [("99213", "Office/outpatient visit, established patient, low MDM", 150, 0.35, False),
               ("99214", "Office/outpatient visit, established patient, moderate MDM", 220, 0.25, False),
               ("99203", "Office/outpatient visit, new patient, low MDM", 200, 0.10, False),
               ("99396", "Preventive visit, established patient, age 40-64", 260, 0.12, False),
               ("80053", "Comprehensive metabolic panel", 60, 0.10, False),
               ("36415", "Routine venipuncture", 25, 0.08, False)],
    "PRV-02": [("99204", "Office/outpatient visit, new patient, moderate MDM", 320, 0.30, False),
               ("99214", "Office/outpatient visit, established patient, moderate MDM", 230, 0.25, False),
               ("20610", "Arthrocentesis/injection, major joint", 280, 0.20, False),
               ("73721", "MRI lower extremity joint without contrast", 1400, 0.13, True),
               ("29881", "Knee arthroscopy with meniscectomy", 4800, 0.12, True)],
    "PRV-03": [("99214", "Office/outpatient visit, established patient, moderate MDM", 230, 0.30, False),
               ("93000", "Electrocardiogram, complete", 90, 0.25, False),
               ("93306", "Transthoracic echocardiogram, complete", 1200, 0.20, True),
               ("93015", "Cardiovascular stress test", 650, 0.15, False),
               ("78452", "Myocardial perfusion imaging, SPECT, multiple studies", 1800, 0.10, True)],
    "PRV-04": [("70553", "MRI brain without and with contrast", 2600, 0.18, True),
               ("72148", "MRI lumbar spine without contrast", 1500, 0.22, True),
               ("74177", "CT abdomen and pelvis with contrast", 1900, 0.18, True),
               ("71046", "Chest X-ray, 2 views", 120, 0.24, False),
               ("77067", "Screening mammography, bilateral", 280, 0.18, False)],
    "PRV-05": [("99392", "Preventive visit, established patient, age 1-4", 220, 0.30, False),
               ("99213", "Office/outpatient visit, established patient, low MDM", 150, 0.35, False),
               ("90460", "Immunization administration with counseling, first component", 45, 0.20, False),
               ("87880", "Rapid strep test", 35, 0.15, False)],
    "PRV-06": [("97110", "Therapeutic exercise, each 15 minutes", 65, 0.40, True),
               ("97140", "Manual therapy techniques, each 15 minutes", 60, 0.25, True),
               ("97161", "Physical therapy evaluation, low complexity", 180, 0.15, False),
               ("97530", "Therapeutic activities, each 15 minutes", 70, 0.20, True)],
    "PRV-07": [("99213", "Office/outpatient visit, established patient, low MDM", 150, 0.35, False),
               ("11102", "Tangential biopsy of skin, single lesion", 210, 0.20, False),
               ("17000", "Destruction of premalignant lesion, first lesion", 160, 0.25, False),
               ("17110", "Destruction of benign lesions, up to 14", 190, 0.20, False)],
    "PRV-08": [("90834", "Psychotherapy, 45 minutes", 160, 0.40, False),
               ("90837", "Psychotherapy, 60 minutes", 210, 0.25, True),
               ("90791", "Psychiatric diagnostic evaluation", 280, 0.15, False),
               ("99214", "Office/outpatient visit, established patient, moderate MDM", 220, 0.20, False)],
}

DIAGNOSES: dict[str, list[tuple[str, str]]] = {
    "PRV-01": [("I10", "Essential (primary) hypertension"), ("E11.9", "Type 2 diabetes mellitus without complications"),
               ("E78.5", "Hyperlipidemia, unspecified"), ("J06.9", "Acute upper respiratory infection, unspecified"),
               ("Z00.00", "Encounter for general adult medical examination without abnormal findings")],
    "PRV-02": [("M17.11", "Unilateral primary osteoarthritis, right knee"), ("M25.561", "Pain in right knee"),
               ("S83.241A", "Other tear of medial meniscus, current injury, right knee, initial encounter"),
               ("M54.50", "Low back pain, unspecified")],
    "PRV-03": [("I25.10", "Atherosclerotic heart disease of native coronary artery without angina pectoris"),
               ("I48.91", "Unspecified atrial fibrillation"), ("R07.9", "Chest pain, unspecified"),
               ("I50.9", "Heart failure, unspecified")],
    "PRV-04": [("G43.909", "Migraine, unspecified, not intractable, without status migrainosus"),
               ("M54.16", "Radiculopathy, lumbar region"), ("R10.9", "Unspecified abdominal pain"),
               ("Z12.31", "Encounter for screening mammogram for malignant neoplasm of breast"),
               ("R05.9", "Cough, unspecified")],
    "PRV-05": [("Z00.129", "Encounter for routine child health examination without abnormal findings"),
               ("J02.0", "Streptococcal pharyngitis"), ("H66.90", "Otitis media, unspecified, unspecified ear"),
               ("Z23", "Encounter for immunization")],
    "PRV-06": [("M54.50", "Low back pain, unspecified"), ("M25.511", "Pain in right shoulder"),
               ("M62.81", "Muscle weakness (generalized)"), ("Z47.1", "Aftercare following joint replacement surgery")],
    "PRV-07": [("L57.0", "Actinic keratosis"), ("D48.5", "Neoplasm of uncertain behavior of skin"),
               ("L82.1", "Other seborrheic keratosis"), ("L70.0", "Acne vulgaris")],
    "PRV-08": [("F32.A", "Depression, unspecified"), ("F41.1", "Generalized anxiety disorder"),
               ("F43.10", "Post-traumatic stress disorder, unspecified"),
               ("F90.0", "Attention-deficit hyperactivity disorder, predominantly inattentive type")],
}

# carc, group, rarc, description, category, preventable, weight (for non-authorization denials)
DENIAL_REASONS = [
    ("16", "CO", "M51", "Claim/service lacks information or has submission/billing error(s)", "missing_information", True, 0.18),
    ("27", "CO", "N30", "Expenses incurred after coverage terminated", "eligibility", True, 0.08),
    ("31", "CO", None, "Patient cannot be identified as our insured", "eligibility", True, 0.05),
    ("50", "CO", "N115", "Non-covered: not deemed a medical necessity by the payer", "medical_necessity", False, 0.14),
    ("11", "CO", None, "The diagnosis is inconsistent with the procedure", "coding", True, 0.10),
    ("4", "CO", None, "The procedure code is inconsistent with the modifier used", "coding", True, 0.06),
    ("97", "CO", None, "Benefit included in the payment/allowance for another service already adjudicated", "coding", True, 0.10),
    ("18", "CO", None, "Exact duplicate claim/service", "duplicate", True, 0.07),
    ("22", "OA", None, "This care may be covered by another payer per coordination of benefits", "coordination_of_benefits", True, 0.07),
    ("29", "CO", None, "The time limit for filing has expired", "timely_filing", True, 0.03),
    ("252", "CO", "M127", "An attachment/other documentation is required to adjudicate this claim/service", "documentation", False, 0.12),
]
AUTH_DENIAL = ("197", "CO", None, "Precertification/authorization/notification absent", "authorization", True)
CODING_DENIALS = [r for r in DENIAL_REASONS if r[0] in ("4", "97")]
RECOVERABLE = {"missing_information", "coding", "documentation", "medical_necessity", "coordination_of_benefits", "authorization"}

REJECTION_REASONS = [
    "Invalid or missing subscriber/member ID (277CA)",
    "Rendering provider NPI missing or invalid (277CA)",
    "Patient date of birth does not match payer records (277CA)",
    "Invalid diagnosis code format (999)",
    "Missing referring provider for specialist service (277CA)",
]

STATES = ["OH", "PA", "MI", "IN", "NY"]


@dataclass
class Scenario:
    cobalt_auth_change: date = date(2026, 5, 1)
    cobalt_slowdown: date = date(2026, 7, 1)


def _business_day(d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _months(start: date, end: date):
    cur = date(start.year, start.month, 1)
    while cur <= end:
        nxt = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
        yield cur, min(nxt - timedelta(days=1), end)
        cur = nxt


def generate(as_of: date, months: int = 18, base_monthly_claims: int = 650, seed: int = 42) -> dict[str, list[dict]]:
    """Return rows for every table, keyed by table name. Deterministic for a given seed/as_of."""
    rng = random.Random(seed)
    sc = Scenario()
    start = date(as_of.year, as_of.month, 1)
    for _ in range(months - 1):
        start = date(start.year - (start.month == 1), (start.month - 2) % 12 + 1, 1)

    payers = [dict(id=p[0], name=p[1], payer_type=p[2], timely_filing_days=p[7], is_synthetic=True) for p in PAYERS]
    providers = [dict(id=p[0], name=p[1], specialty=p[2], provider_type=p[3], state=p[4], is_synthetic=True) for p in PROVIDERS]
    payer_by_id = {p[0]: p for p in PAYERS}

    # Patients: adults (Medicare skewed to 65+) and children (no Medicare).
    patients, adult_pool, child_pool = [], [], []
    for i in range(1, 5201):
        child = i % 6 == 0
        if child:
            payer = rng.choices([p for p in PAYERS if p[2] != "medicare" and p[2] != "medicare_advantage"],
                                weights=[0.35 if p[2] == "medicaid" else 0.65 / 3 for p in PAYERS
                                         if p[2] not in ("medicare", "medicare_advantage")])[0]
            birth_year = rng.randint(as_of.year - 17, as_of.year - 1)
        else:
            payer = rng.choices(PAYERS, weights=[p[3] for p in PAYERS])[0]
            birth_year = (rng.randint(as_of.year - 90, as_of.year - 65) if payer[2] in ("medicare", "medicare_advantage")
                          else rng.randint(as_of.year - 64, as_of.year - 18))
        pid = f"PAT-{i:06d}"
        patients.append(dict(id=pid, birth_year=birth_year, sex=rng.choice("FM"), state=rng.choice(STATES),
                             primary_payer_id=payer[0]))
        (child_pool if child else adult_pool).append((pid, payer[0]))

    claims, payments, denials, history = [], [], [], []
    seq = 0
    for m_idx, (m_start, m_end) in enumerate(_months(start, as_of)):
        n = int(base_monthly_claims * (1 + 0.012 * m_idx) * rng.uniform(0.93, 1.07))
        if m_end == as_of and as_of.day < 28:  # partial current month
            n = int(n * as_of.day / 30)
        for _ in range(n):
            seq += 1
            prov = rng.choices(PROVIDERS, weights=[p[5] for p in PROVIDERS])[0]
            prov_id = prov[0]
            pat_id, payer_id = rng.choice(child_pool if prov_id == "PRV-05" else adult_pool)
            payer = payer_by_id[payer_id]
            proc = rng.choices(PROCEDURES[prov_id], weights=[p[3] for p in PROCEDURES[prov_id]])[0]
            dx = rng.choice(DIAGNOSES[prov_id])

            service_date = _business_day(m_start + timedelta(days=rng.randint(0, (m_end - m_start).days)))
            if service_date > as_of:
                service_date = as_of - timedelta(days=rng.randint(1, 3))
            claim_date = service_date + timedelta(days=max(1, int(rng.gauss(3, 1.5))))
            if claim_date > as_of:
                continue

            units = rng.randint(2, 4) if proc[0] in ("97110", "97140", "97530") else 1
            billed = round(proc[2] * units * rng.uniform(0.95, 1.08), 2)
            modifier = None
            if prov_id == "PRV-07" and proc[0] == "99213" and rng.random() < 0.5:
                modifier = "25"
            elif proc[0] in ("97110", "97140", "97530"):
                modifier = "GP"

            requires_auth = proc[4] and payer[2] != "medicare"
            # S1: Cobalt adds PA for PT/imaging/ortho/cardiac imaging; registration misses many of them.
            if (payer_id == "PYR-COB" and claim_date >= sc.cobalt_auth_change
                    and prov_id in ("PRV-02", "PRV-03", "PRV-04", "PRV-06")):
                requires_auth = True
                auth_missing = rng.random() < 0.5
            else:
                auth_missing = requires_auth and rng.random() < 0.05
            auth_number = None if (not requires_auth or auth_missing) else f"AUTH{rng.randint(10**7, 10**8 - 1)}"

            cid = f"CLM-{seq:06d}"
            row = dict(
                id=cid, patient_id=pat_id, provider_id=prov_id, payer_id=payer_id,
                claim_type="institutional" if prov[3] == "facility" else "professional",
                service_date=service_date, claim_date=claim_date, adjudication_date=None, closed_date=None,
                cpt_code=proc[0], cpt_description=proc[1], modifier=modifier, units=units,
                icd10_code=dx[0], icd10_description=dx[1],
                place_of_service="22" if prov[3] == "facility" else "11",
                authorization_number=auth_number, requires_authorization=requires_auth,
                billed_amount=billed, allowed_amount=0.0, paid_amount=0.0, patient_responsibility=0.0,
                patient_paid_amount=0.0, contractual_adjustment=0.0, writeoff_amount=0.0, balance=billed,
                status="pending", denial_reason_code=None, denial_reason=None, denial_category=None,
                rejection_reason=None, submission_count=1, was_rejected=False, was_denied=False, first_pass_paid=False,
            )
            hist = [dict(claim_id=cid, status="submitted", status_date=claim_date, note="Claim submitted (837) via clearinghouse")]

            # --- Front-end rejection (S4: Medicaid higher) ---
            accepted_date = claim_date + timedelta(days=1)
            p_reject = 0.075 if payer_id == "PYR-MCD" else 0.03
            if rng.random() < p_reject:
                reason = rng.choice(REJECTION_REASONS[:3] if payer_id == "PYR-MCD" else REJECTION_REASONS)
                row.update(was_rejected=True, rejection_reason=reason)
                rej_date = claim_date + timedelta(days=1)
                hist.append(dict(claim_id=cid, status="rejected", status_date=rej_date, note=reason))
                fix_date = rej_date + timedelta(days=rng.randint(2, 9))
                if fix_date > as_of or rng.random() < 0.04:
                    row["status"] = "rejected"
                    _finish(row, hist, claims, history)
                    continue
                row["submission_count"] = 2
                hist.append(dict(claim_id=cid, status="resubmitted", status_date=fix_date, note="Corrected claim resubmitted"))
                accepted_date = fix_date + timedelta(days=1)
            hist.append(dict(claim_id=cid, status="accepted", status_date=accepted_date, note="Accepted by payer (277CA)"))

            # --- Adjudication timing (S2: Cobalt slowdown) ---
            mean, sd = payer[5]
            if payer_id == "PYR-COB" and accepted_date >= sc.cobalt_slowdown:
                mean, sd = 48, 10
            adj_date = accepted_date + timedelta(days=max(7, int(rng.gauss(mean, sd))))
            if adj_date > as_of:
                row["status"] = "pending"
                _finish(row, hist, claims, history)
                continue
            row["adjudication_date"] = adj_date

            allowed = round(billed * rng.uniform(*payer[6]), 2)

            # --- Denial decision ---
            denial = None
            if requires_auth and auth_missing and rng.random() < 0.92:
                denial = AUTH_DENIAL
            else:
                p_deny = payer[4] * prov[6]
                if claim_date.month in (1, 2):  # new plan year: eligibility churn
                    p_deny *= 1.25
                if rng.random() < p_deny:
                    r = rng.choices(DENIAL_REASONS, weights=[d[6] for d in DENIAL_REASONS])[0]
                    denial = r[:6]
                elif prov_id == "PRV-07" and rng.random() < 0.11:  # S3
                    denial = rng.choice(CODING_DENIALS)[:6]

            partial = denial is None and rng.random() < 0.03
            if denial is None and not partial:
                _pay(rng, row, hist, payments, payer, allowed, adj_date, as_of, full=True)
                row["first_pass_paid"] = not row["was_rejected"]
                _finish(row, hist, claims, history)
                continue

            if partial:  # line-level denial on part of the claim
                r = rng.choice([d for d in DENIAL_REASONS if d[0] in ("97", "50")])
                denied_amt = round(allowed * rng.uniform(0.2, 0.5), 2)
                denials.append(_denial_row(cid, r, denied_amt, adj_date, "not_appealed", None, None))
                row.update(was_denied=True, denial_reason_code=r[0], denial_reason=r[3], denial_category=r[4])
                _pay(rng, row, hist, payments, payer, allowed - denied_amt, adj_date, as_of, full=False,
                     billed_allowed=allowed)
                row["writeoff_amount"] = round(row["writeoff_amount"] + denied_amt, 2)
                row["status"] = "partially_paid"
                _recompute_balance(row)
                if row["balance"] <= 0.005:
                    row["closed_date"] = max(h["status_date"] for h in hist)
                _finish(row, hist, claims, history)
                continue

            # --- Full denial ---
            carc, group, rarc, desc, category, preventable = denial
            row.update(was_denied=True, status="denied", denial_reason_code=carc, denial_reason=desc, denial_category=category)
            hist.append(dict(claim_id=cid, status="denied", status_date=adj_date, note=f"Denied: CARC {carc} - {desc}"))
            appeal_date = adj_date + timedelta(days=rng.randint(5, 30))
            appeal_status, resolution_date = "not_appealed", None
            if category in RECOVERABLE and rng.random() < 0.65 and appeal_date <= as_of:
                appeal_status = "pending"
                row["status"] = "appealed"
                row["submission_count"] += 1
                hist.append(dict(claim_id=cid, status="appealed", status_date=appeal_date,
                                 note="Appeal / corrected claim submitted with documentation"))
                decision_date = appeal_date + timedelta(days=rng.randint(25, 60))
                if decision_date <= as_of:
                    resolution_date = decision_date
                    if rng.random() < 0.58:
                        appeal_status = "overturned"
                        hist.append(dict(claim_id=cid, status="appeal_overturned", status_date=decision_date,
                                         note="Appeal approved; claim reprocessed"))
                        _pay(rng, row, hist, payments, payer, allowed, decision_date, as_of, full=True)
                    else:
                        appeal_status = "upheld"
                        row.update(status="denied", writeoff_amount=row["billed_amount"])
                        hist.append(dict(claim_id=cid, status="written_off", status_date=decision_date,
                                         note="Appeal upheld; balance written off"))
            elif (as_of - adj_date).days > 60 and rng.random() < 0.75:
                resolution_date = adj_date + timedelta(days=rng.randint(45, 75))
                if resolution_date <= as_of:
                    row["writeoff_amount"] = row["billed_amount"]
                    hist.append(dict(claim_id=cid, status="written_off", status_date=resolution_date,
                                     note="Denial not recoverable; balance written off"))
                else:
                    resolution_date = None
            denials.append(_denial_row(cid, denial, row["billed_amount"], adj_date, appeal_status,
                                       appeal_date if appeal_status != "not_appealed" else None, resolution_date))
            _recompute_balance(row)
            if row["balance"] <= 0.005 and row["closed_date"] is None:
                row["closed_date"] = resolution_date
            _finish(row, hist, claims, history)

    metadata = {
        "as_of_date": as_of.isoformat(),
        "seed": str(seed),
        "generator": "app.db.synthetic v1",
        "data_notice": "Fully synthetic data. No real patients, payers or providers.",
        "scenarios": json.dumps([
            {"id": "S1", "summary": "Cobalt Mutual Insurance added prior-authorization requirements on 2026-05-01 "
                                    "(imaging, orthopedics, cardiology, physical therapy); many were missed, causing CARC 197 denials."},
            {"id": "S2", "summary": "Cobalt Mutual Insurance slowed adjudication from 2026-07-01 (about 48 days vs 24)."},
            {"id": "S3", "summary": "Lakeside Dermatology has recurring modifier and bundling errors (CARC 4, 97)."},
            {"id": "S4", "summary": "State Medicaid has higher front-end rejection rates (member ID / eligibility)."},
        ]),
    }
    return {
        "payers": payers, "providers": providers, "patients_synthetic": patients, "claims": claims,
        "payments": payments, "denials": denials, "claim_status_history": history,
        "dataset_metadata": [dict(key=k, value=v) for k, v in metadata.items()],
    }


# ----------------------------------------------------------------------------- helpers
def _pay(rng, row, hist, payments, payer, allowed, pay_date, as_of, full: bool, billed_allowed: float | None = None):
    """Post payer payment, contractual adjustment and patient responsibility."""
    contract_allowed = billed_allowed if billed_allowed is not None else allowed
    ptype = payer[2]
    if ptype in ("medicare", "medicare_advantage"):
        pr = allowed * 0.20
    elif ptype == "medicaid":
        pr = min(allowed, 4.0)
    else:
        pr = min(allowed, rng.choice([20, 30, 40, 50])) if row["cpt_code"].startswith("99") else allowed * rng.choice([0.1, 0.2])
        if pay_date.month <= 3 and rng.random() < 0.35:  # deductible season
            pr = min(allowed, pr + rng.uniform(50, 400))
    pr = round(pr, 2)
    paid = round(max(0.0, allowed - pr), 2)
    row["allowed_amount"] = round(contract_allowed, 2)
    row["paid_amount"] = paid
    row["patient_responsibility"] = pr
    row["contractual_adjustment"] = round(row["billed_amount"] - contract_allowed, 2)
    row["status"] = "paid"
    method = "EFT" if rng.random() < 0.85 else "check"
    payments.append(dict(claim_id=row["id"], source="payer", amount=paid, payment_date=pay_date, method=method,
                         trace_number=f"{rng.randint(10**9, 10**10 - 1)}" if method == "EFT" else None))
    hist.append(dict(claim_id=row["id"], status="paid" if full else "partially_paid", status_date=pay_date,
                     note=f"ERA posted: paid {paid:.2f}, patient responsibility {pr:.2f}"))
    if pr > 0:
        pp_date = pay_date + timedelta(days=rng.randint(20, 75))
        if pp_date <= as_of and rng.random() < 0.78:
            row["patient_paid_amount"] = pr
            payments.append(dict(claim_id=row["id"], source="patient", amount=pr, payment_date=pp_date,
                                 method=rng.choice(["card", "card", "check"]), trace_number=None))
            hist.append(dict(claim_id=row["id"], status="patient_paid", status_date=pp_date, note="Patient balance paid"))
    _recompute_balance(row)
    if row["balance"] <= 0.005:
        row["closed_date"] = max(h["status_date"] for h in hist)


def _recompute_balance(row):
    row["balance"] = round(max(0.0, row["billed_amount"] - row["paid_amount"] - row["patient_paid_amount"]
                               - row["contractual_adjustment"] - row["writeoff_amount"]), 2)


def _denial_row(cid, r, amount, d, appeal_status, appeal_date, resolution_date):
    return dict(claim_id=cid, carc_code=r[0], group_code=r[1], rarc_code=r[2], description=r[3], category=r[4],
                preventable=r[5], denied_amount=round(amount, 2), denial_date=d, appeal_status=appeal_status,
                appeal_date=appeal_date, resolution_date=resolution_date)


def _finish(row, hist, claims, history):
    claims.append(row)
    history.extend(hist)
