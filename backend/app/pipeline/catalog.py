"""Reference data for the patient-journey pipeline.

Everything the AI scribe, coder, coverage engine and payer simulator rely on lives here, so the
rules are explicit and testable rather than buried in a model:

* CONDITIONS   spoken phrases -> ICD-10-CM codes (with laterality, specificity and symptom rules)
* SERVICES     orders/procedures -> CPT/HCPCS codes, charges, medical-necessity support, prior-auth
               and coverage rules
* PLANS        benefits per (synthetic) payer: deductible, copays, coinsurance, contract rate
* DOCTORS      fictional clinicians attached to the synthetic provider organisations
* SAMPLES      demo visit conversations that exercise each branch of the workflow

All payers, providers, clinicians and fee amounts are fictional and illustrative. Code
descriptions follow the public ICD-10-CM / HCPCS Level II titles in abbreviated form; CPT
descriptions are paraphrased.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.db.synthetic import PAYERS, PROVIDERS

# --------------------------------------------------------------------------- conditions (ICD-10-CM)


@dataclass(frozen=True)
class Condition:
    key: str
    code: str
    description: str
    phrases: tuple[str, ...]  # regex fragments matched case-insensitively on word boundaries
    kind: str  # acute_minor | acute | acute_complicated | chronic | symptom | preventive
    lateral: dict[str, tuple[str, str]] | None = None  # side -> (code, description)
    integral_to: tuple[str, ...] = ()  # symptom is dropped when one of these dx prefixes is coded
    replaced_by: tuple[tuple[str, str], ...] = ()  # (evidence tag, condition key) specificity upgrades


CONDITIONS: tuple[Condition, ...] = (
    # Infections / acute
    Condition("strep", "J02.0", "Streptococcal pharyngitis", (r"strep throat", r"streptococcal pharyngitis"), "acute"),
    Condition("pharyngitis", "J02.9", "Acute pharyngitis, unspecified",
              (r"sore throat", r"pharyngitis", r"throat (?:is |really )?(?:sore|hurts|pain)"), "acute",
              replaced_by=(("strep_positive", "strep"),)),
    Condition("uri", "J06.9", "Acute upper respiratory infection, unspecified",
              (r"upper respiratory infection", r"common cold", r"head cold", r"\buri\b"), "acute_minor"),
    Condition("influenza", "J11.1", "Influenza with other respiratory manifestations, virus not identified",
              (r"the flu(?! (?:shot|vaccine|test|swab))", r"influenza(?! (?:vaccine|test|shot))"), "acute"),
    Condition("otitis", "H66.90", "Otitis media, unspecified, unspecified ear", (r"ear infection", r"otitis media"), "acute"),
    Condition("uti", "N39.0", "Urinary tract infection, site not specified", (r"urinary tract infection", r"\buti\b", r"bladder infection"), "acute"),
    # Chronic
    Condition("htn", "I10", "Essential (primary) hypertension", (r"hypertension", r"high blood pressure"), "chronic"),
    Condition("dm2_hyper", "E11.65", "Type 2 diabetes mellitus with hyperglycemia", (), "chronic"),
    Condition("dm2", "E11.9", "Type 2 diabetes mellitus without complications",
              (r"type (?:2|two) diabetes", r"diabetes", r"diabetic"), "chronic",
              replaced_by=(("hyperglycemia", "dm2_hyper"),)),
    Condition("hld", "E78.5", "Hyperlipidemia, unspecified", (r"high cholesterol", r"hyperlipidemia", r"cholesterol (?:is |was )?high"), "chronic"),
    Condition("afib", "I48.91", "Unspecified atrial fibrillation", (r"atrial fibrillation", r"\bafib\b", r"\ba-fib\b"), "chronic"),
    Condition("asthma", "J45.909", "Unspecified asthma, uncomplicated", (r"asthma",), "chronic"),
    Condition("gerd", "K21.9", "Gastro-esophageal reflux disease without esophagitis", (r"acid reflux", r"\bgerd\b", r"heartburn"), "chronic"),
    Condition("hypothyroid", "E03.9", "Hypothyroidism, unspecified", (r"hypothyroid(?:ism)?", r"underactive thyroid"), "chronic"),
    Condition("obesity", "E66.9", "Obesity, unspecified", (r"obesity", r"\bobese\b"), "chronic"),
    Condition("gad", "F41.1", "Generalized anxiety disorder", (r"generalized anxiety", r"anxiety disorder", r"\banxiety\b"), "chronic"),
    Condition("depression", "F32.A", "Depression, unspecified", (r"depression", r"\bdepressed\b"), "chronic"),
    Condition("knee_oa", "M17.10", "Unilateral primary osteoarthritis, unspecified knee",
              (r"osteoarthritis (?:of|in) (?:the |your |my )?(?:right |left )?knee", r"(?:right |left )?knee osteoarthritis",
               r"arthritis in (?:the |your |my )?(?:right |left )?knee"), "chronic",
              lateral={"right": ("M17.11", "Unilateral primary osteoarthritis, right knee"),
                       "left": ("M17.12", "Unilateral primary osteoarthritis, left knee")}),
    Condition("radiculopathy", "M54.16", "Radiculopathy, lumbar region",
              (r"radiculopathy", r"sciatica", r"(?:radiat|shoot)\w* down (?:my|the|your) (?:right |left )?leg"), "acute_complicated"),
    Condition("actinic_keratosis", "L57.0", "Actinic keratosis", (r"actinic keratos[ie]s", r"precancerous (?:spot|lesion)s?"), "chronic"),
    Condition("seb_keratosis", "L82.1", "Other seborrheic keratosis", (r"seborrheic keratos[ie]s",), "acute_minor"),
    Condition("vit_d_def", "E55.9", "Vitamin D deficiency, unspecified", (r"vitamin d deficien\w+", r"low vitamin d"), "chronic"),
    Condition("tension_headache", "G44.209", "Tension-type headache, unspecified, not intractable",
              (r"tension[- ]type headaches?", r"tension headaches?"), "acute"),
    Condition("migraine", "G43.909", "Migraine, unspecified, not intractable, without status migrainosus", (r"migraines?",), "chronic"),
    # Symptoms (coded only when no definitive diagnosis explains them)
    Condition("fever", "R50.9", "Fever, unspecified", (r"fevers?", r"temperature of 10\d", r"running a temperature"), "symptom",
              integral_to=("J02", "J06", "J11", "H66", "N39")),
    Condition("cough", "R05.9", "Cough, unspecified", (r"cough(?:ing)?",), "symptom", integral_to=("J06", "J11", "J45")),
    Condition("chest_pain", "R07.9", "Chest pain, unspecified", (r"chest pain", r"pain in (?:my|the|your) chest"), "acute_complicated"),
    Condition("palpitations", "R00.2", "Palpitations", (r"palpitations", r"heart (?:is )?racing", r"heart (?:keeps )?skipping"), "symptom",
              integral_to=("I48",)),
    Condition("headache", "R51.9", "Headache, unspecified", (r"headaches?",), "symptom", integral_to=("G43", "G44")),
    Condition("dysuria", "R30.0", "Dysuria", (r"burn\w* when (?:i |you )?(?:urinate|pee)", r"painful urination", r"dysuria"), "symptom",
              integral_to=("N39",)),
    Condition("abd_pain", "R10.9", "Unspecified abdominal pain", (r"abdominal pain", r"stomach (?:pain|ache)", r"belly pain"), "symptom"),
    Condition("fatigue", "R53.83", "Other fatigue", (r"fatigue", r"tired all the time", r"exhausted", r"no energy"), "symptom"),
    Condition("low_back_pain", "M54.50", "Low back pain, unspecified", (r"(?:low|lower) back pain", r"back pain", r"(?:low|lower) back (?:hurts|(?:has been |is |keeps )?hurting)"),
              "acute", integral_to=("M54.16",)),
    Condition("knee_pain", "M25.569", "Pain in unspecified knee", (r"knee pain", r"knee (?:hurts|has been hurting)", r"pain in (?:my|the|your) (?:right |left )?knee"),
              "symptom", integral_to=("M17",),
              lateral={"right": ("M25.561", "Pain in right knee"), "left": ("M25.562", "Pain in left knee")}),
    # Preventive / encounter
    Condition("annual_exam", "Z00.00", "Encounter for general adult medical examination without abnormal findings",
              (r"annual (?:physical|exam|check-?up|wellness)", r"wellness visit", r"yearly (?:physical|check-?up)", r"routine (?:physical|check-?up)"),
              "preventive"),
    Condition("immunization", "Z23", "Encounter for immunization", (), "preventive"),
)
CONDITION_BY_KEY = {c.key: c for c in CONDITIONS}


# --------------------------------------------------------------------------- services (CPT / HCPCS)

IMAGING_AUTH_PAYERS = ("PYR-MCD", "PYR-NWH", "PYR-COB", "PYR-LSH", "PYR-STC")  # Medicare FFS: no PA for imaging


@dataclass(frozen=True)
class Service:
    code: str
    system: str  # CPT | HCPCS
    description: str
    charge: float
    category: str  # lab | lab_poc | imaging | diagnostic | procedure | drug | vaccine | vaccine_admin
    phrases: tuple[str, ...] = ()
    support: tuple[str, ...] = ()  # ICD-10 prefixes that establish medical necessity; empty = any
    # dx prefix -> evidence tags that must ALL be documented for that dx to support the service
    support_with_evidence: dict[str, tuple[str, ...]] = field(default_factory=dict)
    auth_payers: tuple[str, ...] = ()
    # what happens when necessity is not established: "risk" (may deny; documentation-dependent)
    # or "not_covered" (plan excludes it without a qualifying diagnosis, e.g. screening tests)
    unsupported: str = "risk"
    not_covered_reason: str | None = None
    global_procedure: bool = False  # same-day E/M needs modifier 25
    lateral_modifier: bool = False  # RT / LT
    blood_draw: bool = False  # needs venipuncture 36415


SERVICES: tuple[Service, ...] = (
    # Point-of-care and send-out labs
    Service("87880", "CPT", "Rapid strep test (infectious agent antigen, Strep group A)", 35, "lab_poc",
            (r"rapid strep", r"strep (?:test|swab)", r"swab (?:your|the) throat"), ("J02", "J03", "R50", "R07.0")),
    Service("87804", "CPT", "Rapid influenza test (infectious agent antigen, influenza)", 40, "lab_poc",
            (r"(?:rapid )?flu (?:test|swab)", r"influenza test"), ("J06", "J11", "R50", "R05")),
    Service("81003", "CPT", "Urinalysis, automated, without microscopy", 20, "lab_poc",
            (r"urinalysis", r"urine (?:test|sample|dip)"), ("N39", "R30", "R10", "R31", "E11")),
    Service("87086", "CPT", "Urine culture, bacterial, quantitative colony count", 45, "lab", (r"urine culture",), ("N39", "R30")),
    Service("85025", "CPT", "Complete blood count (CBC) with automated differential", 30, "lab",
            (r"\bcbc\b", r"complete blood count", r"blood count"), ("D64", "R53", "R50", "R10", "N39", "I48", "R00", "Z00"), blood_draw=True),
    Service("80053", "CPT", "Comprehensive metabolic panel", 60, "lab",
            (r"metabolic panel", r"\bcmp\b", r"kidney function", r"liver function"),
            ("E11", "I10", "E78", "R53", "R10", "I48", "N39", "E03", "Z00"), blood_draw=True),
    Service("80061", "CPT", "Lipid panel", 55, "lab",
            (r"lipid panel", r"cholesterol (?:test|panel|level)", r"check (?:your|the) cholesterol"),
            ("E78", "I10", "E11", "I25", "Z00", "E66"), blood_draw=True),
    Service("83036", "CPT", "Hemoglobin A1c", 45, "lab", (r"\ba1c\b", r"hemoglobin a1c", r"glycated hemoglobin"), ("E11", "R73", "E66"), blood_draw=True),
    Service("84443", "CPT", "Thyroid stimulating hormone (TSH)", 50, "lab",
            (r"\btsh\b", r"thyroid (?:test|level|panel|function)"), ("E03", "E05", "R53", "R00", "I48", "E66"), blood_draw=True),
    Service("82306", "CPT", "Vitamin D, 25-hydroxy", 85, "lab",
            (r"vitamin d (?:level|test|blood test)", r"check (?:your|my) vitamin d"), ("E55", "M81", "M80", "N18", "E21", "K90"),
            unsupported="not_covered", blood_draw=True,
            not_covered_reason="Screening vitamin D tests are not covered without a qualifying diagnosis "
                               "(such as documented deficiency, osteoporosis or chronic kidney disease)."),
    Service("36415", "CPT", "Collection of venous blood by venipuncture", 15, "lab"),
    # Diagnostics / imaging
    Service("93000", "CPT", "Electrocardiogram (ECG), complete with interpretation and report", 90, "diagnostic",
            (r"\bekg\b", r"\becg\b", r"electrocardiogram"), ("R07", "I48", "R00", "I10", "I25", "R55", "R06", "Z01.81")),
    Service("71046", "CPT", "Radiologic exam, chest, 2 views", 120, "imaging",
            (r"chest x-?ray",), ("R05", "R07", "J18", "R06", "J11", "R50")),
    Service("73562", "CPT", "Radiologic exam, knee, 3 views", 140, "imaging",
            (r"x-?rays? of (?:the |your |my )?(?:right |left )?knee", r"knee x-?rays?"), ("M17", "M25.56", "S83", "S80"), lateral_modifier=True),
    Service("72100", "CPT", "Radiologic exam, lumbosacral spine, 2-3 views", 130, "imaging",
            (r"x-?rays? of (?:the |your |my )?(?:lower back|lumbar spine|spine)", r"lumbar x-?rays?", r"back x-?rays?"),
            ("M54", "M51", "M48"), support_with_evidence={"M54.5": ("duration_6wk",)}),
    Service("72148", "CPT", "MRI lumbar spine without contrast", 1500, "imaging",
            (r"mri of (?:the |your |my )?(?:lower back|lumbar spine|back|spine)", r"(?:lumbar|back|spine) mri"),
            ("M54.16", "M51.1", "M48.06"), support_with_evidence={"M54.5": ("duration_6wk", "failed_conservative")},
            auth_payers=IMAGING_AUTH_PAYERS),
    Service("73721", "CPT", "MRI lower extremity joint (knee) without contrast", 1400, "imaging",
            (r"mri of (?:the |your |my )?(?:right |left )?knee", r"knee mri"), ("S83", "M23"),
            support_with_evidence={"M25.56": ("failed_conservative",), "M17": ("failed_conservative", "mechanical_symptoms")},
            auth_payers=IMAGING_AUTH_PAYERS, lateral_modifier=True),
    Service("70551", "CPT", "MRI brain without contrast", 1800, "imaging",
            (r"mri of (?:the |your |my )?(?:brain|head)", r"brain mri", r"head mri"), ("G45", "R29.8", "R47", "C71", "G35"),
            support_with_evidence={"R51": ("red_flag_neuro",), "G43": ("red_flag_neuro",), "G44": ("red_flag_neuro",)}, auth_payers=IMAGING_AUTH_PAYERS),
    Service("93306", "CPT", "Transthoracic echocardiogram, complete, with Doppler", 1200, "imaging",
            (r"echocardiogram", r"\becho\b", r"ultrasound of (?:your|the) heart"), ("I48", "I50", "R01", "I35", "R06.0", "I42"),
            auth_payers=IMAGING_AUTH_PAYERS),
    # Procedures and drugs
    Service("20610", "CPT", "Arthrocentesis/injection, major joint, without ultrasound guidance", 280, "procedure",
            (r"(?:steroid|cortisone) (?:injection|shot)", r"inject (?:the|your) (?:right |left )?knee", r"knee injection"),
            ("M17", "M25.56", "M19", "M70"), global_procedure=True, lateral_modifier=True),
    Service("J1030", "HCPCS", "Injection, methylprednisolone acetate, 40 mg", 25, "drug",
            (r"methylprednisolone", r"depo-?medrol"), ("M17", "M25.56", "M19", "M70")),
    Service("17000", "CPT", "Destruction of premalignant lesion (e.g. actinic keratosis), first lesion", 160, "procedure",
            (r"freeze (?:it|them|that|those|the (?:spot|lesion)s?)", r"cryotherapy", r"liquid nitrogen"), ("L57",), global_procedure=True),
    Service("17110", "CPT", "Destruction of benign lesions other than skin tags, up to 14", 190, "procedure",
            (r"remove (?:the |those |these )?(?:benign )?(?:spots|growths|lesions)", r"take (?:it|them|those) off"), ("L82",),
            support_with_evidence={"L82": ("symptomatic_lesion",)}, unsupported="not_covered", global_procedure=True,
            not_covered_reason="Removing asymptomatic seborrheic keratoses is cosmetic and excluded by the plan; "
                               "it is covered only when the lesion is documented as irritated, inflamed or bleeding."),
    Service("11102", "CPT", "Tangential biopsy of skin, single lesion", 210, "procedure",
            (r"\bbiopsy\b", r"shave (?:it|a sample)"), ("D48", "D49", "L57", "L82", "C44", "L98"), global_procedure=True),
    # Vaccines
    Service("90686", "CPT", "Influenza vaccine, quadrivalent, preservative free, IM", 45, "vaccine",
            (r"flu (?:shot|vaccine)", r"influenza vaccine"), ("Z23",)),
    Service("90471", "CPT", "Immunization administration, first vaccine", 30, "vaccine_admin", (), ("Z23",)),
    Service("G0008", "HCPCS", "Administration of influenza virus vaccine (Medicare)", 30, "vaccine_admin", (), ("Z23",)),
    # Behavioral health screening
    Service("96127", "CPT", "Brief emotional/behavioral assessment with scoring (e.g. PHQ-9, GAD-7)", 25, "diagnostic",
            (r"phq-?9", r"gad-?7", r"(?:depression|anxiety) (?:screening )?questionnaire"), ("F32", "F41", "Z13", "Z00", "R45")),
)
SERVICE_BY_CODE = {s.code: s for s in SERVICES}

# E/M and preventive codes (the visit itself)
EM_CODES: dict[str, tuple[str, float]] = {
    "99202": ("Office/outpatient visit, new patient, straightforward MDM", 120),
    "99203": ("Office/outpatient visit, new patient, low MDM", 200),
    "99204": ("Office/outpatient visit, new patient, moderate MDM", 320),
    "99205": ("Office/outpatient visit, new patient, high MDM", 420),
    "99212": ("Office/outpatient visit, established patient, straightforward MDM", 100),
    "99213": ("Office/outpatient visit, established patient, low MDM", 150),
    "99214": ("Office/outpatient visit, established patient, moderate MDM", 220),
    "99215": ("Office/outpatient visit, established patient, high MDM", 300),
    "99382": ("Preventive visit, new patient, age 1-4", 210),
    "99383": ("Preventive visit, new patient, age 5-11", 220),
    "99384": ("Preventive visit, new patient, age 12-17", 230),
    "99392": ("Preventive visit, established patient, age 1-4", 200),
    "99393": ("Preventive visit, established patient, age 5-11", 205),
    "99394": ("Preventive visit, established patient, age 12-17", 215),
    "99385": ("Preventive visit, new patient, age 18-39", 250),
    "99386": ("Preventive visit, new patient, age 40-64", 270),
    "99387": ("Preventive visit, new patient, age 65+", 290),
    "99395": ("Preventive visit, established patient, age 18-39", 230),
    "99396": ("Preventive visit, established patient, age 40-64", 260),
    "99397": ("Preventive visit, established patient, age 65+", 280),
    "G0438": ("Annual wellness visit, initial (Medicare)", 280),
    "G0439": ("Annual wellness visit, subsequent (Medicare)", 210),
}

NCCI_EDITS: tuple[tuple[str, str, str], ...] = (
    # (column 1, column 2, note): column 2 is bundled into column 1 when billed together
    ("80053", "82947", "Glucose is a component of the comprehensive metabolic panel"),
    ("85025", "85027", "CBC without differential is included in CBC with differential"),
    ("81003", "81001", "Automated urinalysis codes are mutually exclusive"),
    ("20610", "20611", "Injection with and without ultrasound guidance are mutually exclusive"),
)

VALID_MODIFIERS = {"25", "RT", "LT", "GA", "59", "XS"}

# --------------------------------------------------------------------------- payers, plans, people


@dataclass(frozen=True)
class Plan:
    payer_id: str
    plan_name: str
    deductible: float
    copay_pcp: float
    copay_specialist: float
    coinsurance: float
    allowed_ratio: float  # contracted rate as a share of billed charge
    adjudication_days: int
    member_id_pattern: str
    member_id_example: str
    oop_max: float


PLANS: dict[str, Plan] = {
    "PYR-MCR": Plan("PYR-MCR", "Original Medicare Part B", 257, 0, 0, 0.20, 0.47, 16, r"^[1-9][A-Z][A-Z0-9]\d[A-Z][A-Z0-9]\d[A-Z]{2}\d{2}$", "1EG4TE5MK72", 0),
    "PYR-MCD": Plan("PYR-MCD", "State Medicaid Managed Care", 0, 0, 0, 0.0, 0.38, 34, r"^\d{10}$", "4410028931", 0),
    "PYR-NWH": Plan("PYR-NWH", "Northwind PPO Gold", 1500, 25, 50, 0.20, 0.64, 21, r"^NWH\d{8}$", "NWH20418833", 6500),
    "PYR-COB": Plan("PYR-COB", "Cobalt Choice HMO", 2000, 30, 60, 0.20, 0.66, 24, r"^COB\d{8}$", "COB55120764", 7500),
    "PYR-LSH": Plan("PYR-LSH", "Lakeshore Medicare Advantage", 0, 10, 40, 0.20, 0.53, 28, r"^LSH\d{8}$", "LSH70031245", 4900),
    "PYR-STC": Plan("PYR-STC", "Sterling Care Silver PPO", 1000, 20, 40, 0.10, 0.70, 18, r"^STC\d{8}$", "STC91022008", 5000),
}
PAYER_INFO = {p[0]: {"name": p[1], "payer_type": p[2], "timely_filing_days": p[7]} for p in PAYERS}


@dataclass(frozen=True)
class Doctor:
    id: str
    name: str
    provider_id: str
    specialty: str
    npi: str  # synthetic 10-digit identifier (not a real NPI)
    primary_care: bool


DOCTORS: tuple[Doctor, ...] = (
    Doctor("DR-01", "Dr. Maya Chen", "PRV-01", "Family Medicine", "1902846613", True),
    Doctor("DR-02", "Dr. Omar Haddad", "PRV-01", "Family Medicine", "1730219954", True),
    Doctor("DR-03", "Dr. Lena Brooks", "PRV-02", "Orthopedic Surgery", "1588012477", False),
    Doctor("DR-04", "Dr. Samuel Okafor", "PRV-03", "Cardiology", "1467703385", False),
    Doctor("DR-05", "Dr. Priya Nair", "PRV-05", "Pediatrics", "1356678120", True),
    Doctor("DR-06", "Dr. Elena Varga", "PRV-07", "Dermatology", "1245590036", False),
    Doctor("DR-07", "Dr. Jonah Reyes", "PRV-08", "Behavioral Health", "1134482219", False),
)
DOCTOR_BY_ID = {d.id: d for d in DOCTORS}
PROVIDER_INFO = {p[0]: {"name": p[1], "specialty": p[2], "provider_type": p[3], "state": p[4]} for p in PROVIDERS}
PROVIDER_TAX_ID = {p[0]: f"{90 + i:02d}-{1234500 + i * 37:07d}" for i, p in enumerate(PROVIDERS)}


def claim_form(provider_id: str) -> tuple[str, str]:
    """(paper form, electronic transaction) for the care setting (slide 8)."""
    if PROVIDER_INFO.get(provider_id, {}).get("provider_type") == "facility":
        return "UB-04", "837I"
    return "CMS-1500", "837P"


# --------------------------------------------------------------------------- medications (for MDM risk)

PRESCRIPTION_DRUGS = (
    "amoxicillin", "azithromycin", "augmentin", "cephalexin", "nitrofurantoin", "ciprofloxacin", "doxycycline",
    "lisinopril", "losartan", "amlodipine", "hydrochlorothiazide", "metoprolol", "metformin", "glipizide",
    "jardiance", "ozempic", "insulin", "atorvastatin", "rosuvastatin", "simvastatin", "levothyroxine",
    "sertraline", "escitalopram", "fluoxetine", "bupropion", "omeprazole", "pantoprazole", "prednisone",
    "albuterol", "fluticasone", "meloxicam", "cyclobenzaprine", "gabapentin", "sumatriptan", "apixaban",
    "eliquis", "warfarin", "oseltamivir", "tamiflu", "tretinoin", "methylprednisolone", "depo-medrol",
)
OTC_DRUGS = ("ibuprofen", "advil", "motrin", "tylenol", "acetaminophen", "naproxen", "aleve", "antihistamine",
             "zyrtec", "claritin", "vitamin d supplement", "over the counter", "over-the-counter")

# --------------------------------------------------------------------------- evidence tags (necessity)

EVIDENCE_PATTERNS: dict[str, tuple[str, ...]] = {
    "strep_positive": (r"strep[^.?!]{0,40}\b(?:is|was|came back|came out|shows?)\s+positive", r"positive (?:rapid )?strep"),
    "hyperglycemia": (r"(?:sugars?|glucose|a1c)[^.?!]{0,30}\b(?:high|elevated|running high|up|over \d+)", r"hyperglycemi\w+",
                      r"(?:diabetes|sugars?)[^.?!]{0,25}(?:not|isn't|poorly|aren't) (?:well )?controlled", r"uncontrolled (?:diabetes|sugars?)"),
    "duration_6wk": (r"\b(?:six|seven|eight|nine|ten|twelve|6|7|8|9|10|12|several) weeks", r"\b(?:a|one|two|three|four|five|six|\d+|couple of|few) months?\b",
                     r"since last (?:year|summer|winter|spring|fall)"),
    "failed_conservative": (r"tried[^.?!]{0,40}(?:physical therapy|\bpt\b|ibuprofen|advil|naproxen|anti-?inflammator\w*|stretch\w*|rest|exercises|brace)",
                            r"(?:physical therapy|\bpt\b|ibuprofen|medication|exercises|injections?)[^.?!]{0,30}(?:didn't|did not|hasn't|has not|isn't|not) (?:really )?help",
                            r"failed (?:conservative|physical therapy)"),
    "mechanical_symptoms": (r"\blocking\b", r"\blocks? up\b", r"\bcatching\b", r"\bcatches\b", r"gives? (?:way|out)", r"\bclicking\b", r"\bpopping\b"),
    "red_flag_neuro": (r"worst headache", r"thunderclap", r"(?:vision|speech) (?:changes|loss|problems)", r"weakness (?:on|in) (?:one|the (?:left|right))",
                       r"\bnumbness\b[^.?!]{0,30}(?:face|arm)", r"\bseizures?\b", r"new (?:onset )?headaches? (?:after|over) (?:age )?50"),
    "symptomatic_lesion": (r"(?:spot|lesion|growth)s?[^.?!]{0,30}(?:bleed\w*|irritated|inflamed|itch\w*|catch\w* on)", r"(?:bleed\w*|irritated|inflamed)[^.?!]{0,30}(?:spot|lesion|growth)"),
    "worsening": (r"getting worse", r"worsening", r"(?:not|isn't|aren't|poorly) (?:well )?controlled", r"uncontrolled", r"running high"),
}
EVIDENCE_RE = {k: tuple(re.compile(p, re.I) for p in v) for k, v in EVIDENCE_PATTERNS.items()}
EVIDENCE_LABELS = {
    "strep_positive": "Positive rapid strep result documented",
    "hyperglycemia": "Elevated glucose / poor control documented",
    "duration_6wk": "Symptom duration of 6+ weeks documented",
    "failed_conservative": "Failed conservative treatment documented",
    "mechanical_symptoms": "Mechanical symptoms (locking, catching, giving way) documented",
    "red_flag_neuro": "Neurological red-flag symptoms documented",
    "symptomatic_lesion": "Lesion documented as symptomatic (irritated, inflamed or bleeding)",
    "worsening": "Condition documented as worsening or uncontrolled",
}

# --------------------------------------------------------------------------- simulated payer responses

REJECTION_SCENARIOS = (
    ("A7:33", "Subscriber name does not match payer records",
     "Re-ran a 270/271 demographic match and corrected the subscriber name to the payer's spelling."),
    ("A7:164", "Entity's contract/member number invalid for date of service",
     "Re-verified eligibility for the date of service and corrected the member number suffix."),
    ("A6:21", "Missing or invalid billing provider taxonomy code",
     "Added the billing provider taxonomy from the provider master file."),
)
SELF_PAY_DISCOUNT = 0.60  # self-pay price as a share of the billed charge
PATIENT_PORTAL_URL = "https://pay.example-clinic.test"  # placeholder shown on statements

# --------------------------------------------------------------------------- demo conversations

SAMPLES: tuple[dict, ...] = (
    {
        "id": "strep",
        "title": "Sore throat and fever",
        "summary": "Acute visit; point-of-care strep test comes back positive; antibiotics prescribed. Clean claim, paid first pass.",
        "provider_id": "PRV-01", "doctor_id": "DR-01", "payer_id": "PYR-NWH", "visit_reason": "Sore throat and fever",
        "new_patient": False, "birth_year": 1991, "sex": "F",
        "transcript": [
            ("doctor", "Hi, what brings you in today?"),
            ("patient", "I've had a really bad sore throat for three days and a fever since yesterday."),
            ("doctor", "Any cough or runny nose?"),
            ("patient", "No, no cough at all. It just hurts to swallow."),
            ("doctor", "Your temperature is 101.4 degrees today. Let me take a look. Your tonsils are red and swollen with some white patches, and the lymph nodes in your neck are tender."),
            ("doctor", "I'd like to do a rapid strep test. I'll swab your throat now."),
            ("doctor", "Okay, the rapid strep came back positive, so this is strep throat."),
            ("doctor", "I'm going to prescribe amoxicillin for ten days. You can take ibuprofen for the pain and fever."),
            ("patient", "Okay, thank you."),
            ("doctor", "Follow up if you're not feeling better in 48 to 72 hours."),
        ],
    },
    {
        "id": "diabetes",
        "title": "Diabetes and blood pressure follow-up",
        "summary": "Chronic care visit with labs; patient also asks for a vitamin D test that the plan will not cover, caught before the claim goes out.",
        "provider_id": "PRV-01", "doctor_id": "DR-02", "payer_id": "PYR-STC", "visit_reason": "Diabetes and hypertension follow-up",
        "new_patient": False, "birth_year": 1968, "sex": "M",
        "transcript": [
            ("doctor", "Good to see you again. How have your sugars been?"),
            ("patient", "Not great. My morning sugars have been running high, around 180 to 200."),
            ("doctor", "And are you taking the metformin every day?"),
            ("patient", "Yes, twice a day."),
            ("doctor", "Your blood pressure today is 148 over 92, which is higher than we want. Your type 2 diabetes is not well controlled, and your high blood pressure is getting worse."),
            ("doctor", "Any chest pain or shortness of breath?"),
            ("patient", "No."),
            ("doctor", "I'm going to order a hemoglobin A1c, a lipid panel and a comprehensive metabolic panel to check your kidney function."),
            ("patient", "Could you also check my vitamin D? I read that a lot of people are low and I've been feeling tired."),
            ("doctor", "Sure, we can add a vitamin D level."),
            ("doctor", "I'm increasing your metformin to 1000 milligrams twice a day and starting lisinopril 10 milligrams daily for your blood pressure."),
            ("doctor", "Let's follow up in three months."),
        ],
    },
    {
        "id": "knee",
        "title": "Knee pain: injection and MRI",
        "summary": "New orthopedic patient; same-day steroid injection (modifier 25, RT, J-code) and an MRI that needs prior authorization, approved because conservative care failed.",
        "provider_id": "PRV-02", "doctor_id": "DR-03", "payer_id": "PYR-COB", "visit_reason": "Right knee pain",
        "new_patient": True, "birth_year": 1964, "sex": "F",
        "transcript": [
            ("doctor", "What's going on with your knee?"),
            ("patient", "My right knee has been hurting for about four months. Some days it locks up and catches when I walk down stairs."),
            ("doctor", "What have you tried so far?"),
            ("patient", "I tried physical therapy for six weeks and ibuprofen, but it didn't really help."),
            ("doctor", "On exam there's swelling and tenderness along the inside of the right knee, with reduced range of motion."),
            ("doctor", "Let's get x-rays of the right knee today."),
            ("doctor", "The x-rays show osteoarthritis of the right knee with narrowing of the joint space."),
            ("doctor", "Because of the locking and catching, I want an MRI of the right knee to look for a meniscus tear."),
            ("doctor", "For the pain, I'd like to give you a steroid injection in the right knee today with methylprednisolone 40 milligrams."),
            ("patient", "Okay, let's do that."),
            ("doctor", "Follow up after the MRI in two weeks."),
        ],
    },
    {
        "id": "back",
        "title": "Back pain: MRI the plan will not approve",
        "summary": "Two weeks of back pain without red flags; the patient wants an MRI. Prior authorization is denied before the scan, so no surprise bill and no claim denial.",
        "provider_id": "PRV-01", "doctor_id": "DR-01", "payer_id": "PYR-NWH", "visit_reason": "Low back pain",
        "new_patient": False, "birth_year": 1985, "sex": "M",
        "transcript": [
            ("doctor", "What can I help you with today?"),
            ("patient", "My lower back has been hurting for about two weeks since I moved some furniture."),
            ("doctor", "Does the pain shoot down either leg? Any numbness or tingling?"),
            ("patient", "No, it stays in my back."),
            ("doctor", "Any problems with your bladder or bowels, fever, or weight loss?"),
            ("patient", "No, nothing like that."),
            ("doctor", "On exam you have tenderness of the lower back muscles, normal strength and normal reflexes in both legs."),
            ("patient", "Can I get an MRI? I want to make sure nothing is seriously wrong."),
            ("doctor", "I'll order an MRI of the lower back, but most back strains like this get better in a few weeks without imaging."),
            ("doctor", "In the meantime take ibuprofen, use heat, and I'm prescribing cyclobenzaprine to help with the muscle spasms at night."),
            ("doctor", "Come back in four weeks if it isn't improving."),
        ],
    },
    {
        "id": "wellness",
        "title": "Medicare wellness visit, flu shot and palpitations",
        "summary": "Medicare annual wellness visit (G0439), flu vaccine with Medicare's own admin code (G0008), and a separate palpitations work-up billed with modifier 25.",
        "provider_id": "PRV-01", "doctor_id": "DR-02", "payer_id": "PYR-MCR", "visit_reason": "Annual wellness visit",
        "new_patient": False, "birth_year": 1952, "sex": "F",
        "transcript": [
            ("doctor", "Welcome in for your annual wellness visit. How have you been feeling overall?"),
            ("patient", "Mostly good. But over the last month I've noticed my heart racing sometimes, for a few minutes at a time."),
            ("doctor", "Any chest pain or fainting with it?"),
            ("patient", "No chest pain, and I haven't fainted."),
            ("doctor", "Your blood pressure is 128 over 78 and your heart rate is 84 and regular right now. We reviewed your medications, fall risk and your preventive care schedule."),
            ("doctor", "For the palpitations, let's do an EKG today and I'll order a thyroid test and a complete blood count."),
            ("doctor", "Have you had your flu shot this year?"),
            ("patient", "No, not yet."),
            ("doctor", "We'll give you the flu shot today as well."),
            ("doctor", "If the palpitations get worse or you feel faint, call us right away. Otherwise I'll see you in one year."),
        ],
    },
    {
        "id": "headache",
        "title": "Medicare headache: MRI without red flags",
        "summary": "Medicare patient with ordinary headaches asks for a brain MRI. It is flagged as a medical-necessity risk, an ABN is signed (modifier GA), the payer denies it and the AI routes the balance to the patient instead of a doomed appeal.",
        "provider_id": "PRV-01", "doctor_id": "DR-01", "payer_id": "PYR-MCR", "visit_reason": "Headaches",
        "new_patient": False, "birth_year": 1956, "sex": "M",
        "transcript": [
            ("doctor", "Tell me about the headaches."),
            ("patient", "I get headaches a couple of times a week, mostly in the afternoon. Tylenol usually helps."),
            ("doctor", "Any vision changes, weakness, numbness, or trouble speaking?"),
            ("patient", "No, none of that."),
            ("doctor", "Your neurological exam is normal today. These sound like tension type headaches."),
            ("patient", "My neighbor had a brain tumor. I'd really like a brain MRI to be safe."),
            ("doctor", "I understand. I'll order an MRI of the brain, but Medicare may not pay for it without warning signs, so we'll ask you to sign a notice first."),
            ("doctor", "Keep a headache diary, and you can keep using acetaminophen as needed."),
            ("doctor", "Follow up in six weeks."),
        ],
    },
)
SAMPLE_BY_ID = {s["id"]: s for s in SAMPLES}
