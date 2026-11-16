"""Patient-journey pipeline: scribe, coding, coverage and the booking-to-cash workflow."""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.pipeline import catalog as cat
from app.pipeline import coding, coverage, scribe

# --------------------------------------------------------------------------- scribe


def _extract(*turns):
    return scribe.extract([scribe.Utterance(s, t) for s, t in turns])


def test_negation_question_answer_and_uncertainty():
    r = _extract(
        ("doctor", "Any chest pain?"), ("patient", "No."),
        ("patient", "I have a fever and no cough."),
        ("doctor", "This could be strep throat."),
        ("patient", "My mother has diabetes."),
    )
    assert set(r.conditions) == {"fever"}
    held = {m.key: m.status for m in r.not_coded}
    assert held == {"chest_pain": "negated", "cough": "negated", "strep": "uncertain", "dm2": "other_person"}


def test_orders_only_from_clinician_statements():
    r = _extract(
        ("patient", "Can I get an MRI of my lower back?"),
        ("doctor", "Have you had your flu shot this year?"), ("patient", "No."),
        ("doctor", "You had a chest x-ray last year."),
        ("doctor", "Let's do an EKG today."),
    )
    assert set(r.orders) == {"71046", "93000"}
    assert r.orders["71046"].status == "reviewed" and r.orders["93000"].status == "ordered"


def test_parse_labelled_transcript():
    u = scribe.parse_transcript("Doctor: Hello.\nPatient: My knee hurts.\nit has for weeks\nDr: Okay.")
    assert [x.speaker for x in u] == ["doctor", "patient", "doctor"]
    assert u[1].text == "My knee hurts. it has for weeks"


# --------------------------------------------------------------------------- coding + coverage per sample

EXPECTED = {
    "strep": ({"J02.0"}, {"99213", "87880"}),
    "diabetes": ({"E11.65", "I10"}, {"99214", "83036", "80061", "80053", "82306", "36415"}),
    "knee": ({"M17.11"}, {"99204", "73562", "73721", "20610", "J1030"}),
    "back": ({"M54.50"}, {"99213", "72148"}),
    "wellness": ({"Z00.00", "R00.2", "Z23"}, {"G0439", "99213", "85025", "84443", "93000", "90686", "G0008", "36415"}),
    "headache": ({"G44.209"}, {"99213", "70551"}),
}


def _code_sample(sid):
    s = cat.SAMPLE_BY_ID[sid]
    r = _extract(*s["transcript"])
    return r, coding.code_encounter(r, payer_id=s["payer_id"], new_patient=s["new_patient"], age=2026 - s["birth_year"])


@pytest.mark.parametrize("sid", list(EXPECTED))
def test_sample_coding(sid):
    _, c = _code_sample(sid)
    dx, services = EXPECTED[sid]
    assert {d["code"] for d in c.diagnoses} == dx
    assert {ln["code"] for ln in c.lines} == services


def test_specificity_modifiers_and_primary_dx():
    _, knee = _code_sample("knee")
    by = {ln["code"]: ln for ln in knee.lines}
    assert by["99204"]["modifier"] == "25" and by["20610"]["modifier"] == "RT" and by["73721"]["modifier"] == "RT"
    _, dm = _code_sample("diabetes")
    assert dm.diagnoses[0]["code"] == "E11.65" and dm.diagnoses[0]["primary"]
    _, well = _code_sample("wellness")
    assert {ln["code"]: ln["modifier"] for ln in well.lines}["99213"] == "25"
    assert {ln["code"]: ln["dx_codes"] for ln in well.lines}["85025"] == ["R00.2"]  # not the wellness Z code


@pytest.mark.parametrize("sid,code,status,decision", [
    ("diabetes", "82306", "not_covered", "self_pay"),
    ("knee", "73721", "prior_auth_required", "bill_insurance"),
    ("back", "72148", "prior_auth_required", "bill_insurance"),
    ("headache", "70551", "medical_necessity_risk", "bill_with_abn"),
    ("strep", "87880", "covered", "bill_insurance"),
])
def test_coverage_decisions(sid, code, status, decision):
    r, c = _code_sample(sid)
    ln = next(x for x in c.lines if x["code"] == code)
    cov = coverage.determine_coverage(ln, cat.SAMPLE_BY_ID[sid]["payer_id"], [d["code"] for d in c.diagnoses], r.evidence)
    assert (cov["coverage_status"], cov["billing_decision"]) == (status, decision)


def test_prior_auth_approves_supported_and_denies_unsupported():
    for sid, expect in (("knee", "approved"), ("back", "denied")):
        r, c = _code_sample(sid)
        dx = [d["code"] for d in c.diagnoses]
        for ln in c.lines:
            ln.update(coverage.determine_coverage(ln, cat.SAMPLE_BY_ID[sid]["payer_id"], dx, r.evidence))
        res = coverage.request_authorizations(c.lines, cat.SAMPLE_BY_ID[sid]["payer_id"], dx, r.evidence, "ENC-000001")
        assert [x["status"] for x in res] == [expect]


def test_eligibility_rules():
    ok = coverage.verify_eligibility("PYR-NWH", "NWH20418833", date(2026, 11, 20), specialist=False)
    assert ok["active"] and ok["copay"] == 25 and 0 <= ok["deductible_remaining"] <= 1500
    assert coverage.verify_eligibility("PYR-NWH", "BAD1", date(2026, 11, 20), False)["error_code"] == "AAA*72"
    assert coverage.verify_eligibility("PYR-NWH", "NWH20410000", date(2026, 11, 20), False)["error_code"] == "EB*6"


def test_pricing_copay_deductible_and_medicare_rules():
    elig = {"copay": 25, "deductible_remaining": 100}
    lines = [{"code": "99213", "charge": 150, "category": "em"}, {"code": "80053", "charge": 60, "category": "lab"},
             {"code": "71046", "charge": 120, "category": "imaging"}]
    t = coverage.price_lines(lines, "PYR-NWH", elig)
    assert lines[0]["est_patient"] == 25  # copay only
    assert lines[1]["cost_share"]["deductible"] == pytest.approx(38.4)  # whole allowed amount to deductible
    assert t["payer"] + t["patient"] == pytest.approx(t["allowed"])
    mcr = [{"code": "80053", "charge": 60, "category": "lab"}, {"code": "G0439", "charge": 210, "category": "em"}]
    coverage.price_lines(mcr, "PYR-MCR", {"deductible_remaining": 257})
    assert mcr[0]["est_patient"] == 0 and mcr[1]["est_patient"] == 0  # Medicare labs and AWV: no cost share


# --------------------------------------------------------------------------- end-to-end via the API


@pytest.fixture(scope="module")
def client(seeded_db):
    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


_slot = [0]


def _book(client, sid, **over):
    s = cat.SAMPLE_BY_ID[sid]
    _slot[0] += 1
    when = datetime.combine(date.today() + timedelta(days=1 + _slot[0] // 14), datetime.min.time()).replace(hour=9) \
        + timedelta(minutes=30 * (_slot[0] % 14))
    body = {"patient_name": "Test Patient", "birth_year": s["birth_year"], "sex": s["sex"], "state": "OH",
            "payer_id": s["payer_id"], "member_id": cat.PLANS[s["payer_id"]].member_id_example, "doctor_id": s["doctor_id"],
            "scheduled_at": when.isoformat(), "visit_reason": s["visit_reason"], "new_patient": s["new_patient"]} | over
    r = client.post("/api/encounters", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _through_visit(client, sid):
    enc = _book(client, sid)
    eid = enc["id"]
    assert enc["stage"] == "authorization_checked"
    r = client.post(f"/api/encounters/{eid}/autopilot").json()
    assert r["stage"] == "in_consultation" and r["attention"] == "consultation"
    utts = [{"speaker": a, "text": b} for a, b in cat.SAMPLE_BY_ID[sid]["transcript"]]
    assert client.post(f"/api/encounters/{eid}/transcript", json={"utterances": utts}).status_code == 200
    r = client.post(f"/api/encounters/{eid}/scribe").json()
    assert r["stage"] == "coded" and r["attention"] == "sign_off" and r["note"]["assessment"]
    r = client.post(f"/api/encounters/{eid}/sign").json()
    assert r["signed"] and r["attention"] is None
    return eid, client.post(f"/api/encounters/{eid}/autopilot").json()


@pytest.mark.parametrize("sid", ["strep", "diabetes", "knee", "back", "wellness"])
def test_booking_to_closed_account(client, sid):
    eid, r = _through_visit(client, sid)
    if r["attention"] == "denial":
        r = client.post(f"/api/encounters/{eid}/denial", json={"action": "appeal"}).json()
        r = client.post(f"/api/encounters/{eid}/autopilot").json()
    if r["attention"] == "patient_payment":
        r = client.post(f"/api/encounters/{eid}/patient-payment", json={}).json()
        r = client.post(f"/api/encounters/{eid}/autopilot").json()
    assert r["stage"] == "closed", (r["stage"], r["attention"], r["attention_detail"])
    assert abs(r["balance"]) < 0.01
    steps = {e["step"] for e in r["events"]}
    assert steps == set(range(1, 16)) or steps >= set(range(1, 16)) - {11, 12, 13}  # self-pay-only visits skip the payer
    t = r["totals"]
    assert t["payer_paid"] + t["patient_paid"] + t["adjustments"] == pytest.approx(t["total_charge"], abs=0.02)
    for ln in r["lines"]:
        if ln["claim_id"]:
            c = client.get(f"/api/claims/{ln['claim_id']}").json()
            assert c["balance"] == 0 and c["status"] in ("paid", "denied")


def test_back_pain_mri_is_not_performed(client):
    _, r = _through_visit(client, "back")
    mri = next(ln for ln in r["lines"] if ln["code"] == "72148")
    assert mri["auth_status"] == "denied" and mri["billing_decision"] == "do_not_perform" and mri["claim_id"] is None


def test_medicare_abn_denial_goes_to_patient(client):
    eid, r = _through_visit(client, "headache")
    mri = next(ln for ln in r["lines"] if ln["code"] == "70551")
    assert "GA" in (mri["modifier"] or "") and mri["carc"] == "PR-50" and mri["patient_resp"] > 0
    assert r["attention"] == "patient_payment"  # no appeal: ABN makes the patient responsible
    assert any("routed to the patient" in e["title"] for e in r["events"])


def test_vitamin_d_is_self_pay_and_billed_to_patient(client):
    _, r = _through_visit(client, "diabetes")
    vit = next(ln for ln in r["lines"] if ln["code"] == "82306")
    assert vit["billing_decision"] == "self_pay" and vit["claim_id"] is None
    assert any(i["code"] == "82306" for i in r["billing"]["statement"]["items"])


def test_eligibility_failure_blocks_until_fixed(client):
    enc = _book(client, "strep", member_id="WRONG123")
    assert enc["attention"] == "eligibility" and enc["stage"] == "registered"
    assert client.post(f"/api/encounters/{enc['id']}/advance").json()["result"]["advanced"] is False
    fixed = client.post(f"/api/encounters/{enc['id']}/registration", json={"member_id": "NWH20418833"}).json()
    assert fixed["attention"] is None and fixed["stage"] == "authorization_checked"


def test_coding_edit_recomputes_coverage(client):
    enc = _book(client, "strep")
    eid = enc["id"]
    client.post(f"/api/encounters/{eid}/autopilot")
    utts = [{"speaker": a, "text": b} for a, b in cat.SAMPLE_BY_ID["strep"]["transcript"]]
    client.post(f"/api/encounters/{eid}/transcript", json={"utterances": utts})
    client.post(f"/api/encounters/{eid}/scribe")
    r = client.post(f"/api/encounters/{eid}/coding", json={
        "diagnoses": ["J02.0"], "lines": [{"code": "99214"}, {"code": "87880"}, {"code": "82306"}]}).json()
    by = {ln["code"]: ln for ln in r["lines"]}
    assert by["82306"]["coverage_status"] == "not_covered" and by["99214"]["source"] == "manual"
    assert client.post(f"/api/encounters/{eid}/coding", json={"diagnoses": ["XYZ"], "lines": [{"code": "99213"}]}).status_code == 422
    assert client.post(f"/api/encounters/{eid}/coding", json={"diagnoses": ["A00.0"], "lines": [{"code": "99213"}]}).status_code == 409


def test_guards_and_validation(client):
    assert client.get("/api/encounters/ENC-999999").status_code == 404
    assert client.get("/api/encounters/bogus").status_code == 422
    enc = _book(client, "strep")
    assert client.post(f"/api/encounters/{enc['id']}/sign").status_code == 409
    assert client.post(f"/api/encounters/{enc['id']}/patient-payment", json={}).status_code == 409
    dup = client.post("/api/encounters", json={
        "patient_name": "Other Person", "birth_year": 1990, "sex": "M", "state": "OH", "payer_id": "PYR-NWH",
        "member_id": "NWH20418833", "doctor_id": cat.SAMPLE_BY_ID["strep"]["doctor_id"], "scheduled_at": enc["scheduled_at"],
        "visit_reason": "x y", "new_patient": False})
    assert dup.status_code == 409
    assert client.post("/api/encounters", json={"patient_name": "<script>", "birth_year": 1990}).status_code == 422


def test_list_scorecard_and_options(client):
    body = client.get("/api/encounters").json()
    assert body["items"] and body["scorecard"]["encounters"] == len(body["items"])
    assert body["scorecard"]["closed"] >= 1 and body["scorecard"]["automated_steps"] > body["scorecard"]["human_actions"]
    opts = client.get("/api/encounters/options").json()
    assert len(opts["stages"]) == 15 and opts["samples"] and opts["doctors"]
    assert client.get("/api/encounters/codes", params={"q": "knee"}).json()["diagnoses"]


def test_rejection_pend_and_appeal_loop(client, monkeypatch):
    """Force a 277CA rejection and a payer pend, and bill an unsupported EKG so it is denied CO-50."""
    from app.pipeline import revenue

    real = revenue.stable_fraction
    monkeypatch.setattr(revenue, "stable_fraction", lambda *p: 0.0 if p[-1] in ("277ca", "pend") else real(*p))
    enc = _book(client, "strep")
    eid = enc["id"]
    client.post(f"/api/encounters/{eid}/autopilot")
    utts = [{"speaker": a, "text": b} for a, b in cat.SAMPLE_BY_ID["strep"]["transcript"]]
    client.post(f"/api/encounters/{eid}/transcript", json={"utterances": utts})
    client.post(f"/api/encounters/{eid}/scribe")
    # An EKG for strep throat has no supporting diagnosis -> denial risk, billed anyway; drug units push the claim over $1,000.
    r = client.post(f"/api/encounters/{eid}/coding", json={"diagnoses": ["J02.0"], "lines": [
        {"code": "99213"}, {"code": "87880"}, {"code": "93000", "billing_decision": "bill_insurance"},
        {"code": "71046", "billing_decision": "bill_insurance"},
        {"code": "J1030", "units": 34, "billing_decision": "bill_insurance"}]}).json()
    assert next(ln for ln in r["lines"] if ln["code"] == "93000")["coverage_status"] == "medical_necessity_risk"
    client.post(f"/api/encounters/{eid}/sign")
    r = client.post(f"/api/encounters/{eid}/autopilot").json()
    titles = [e["title"] for e in r["events"]]
    assert any("277CA rejection" in t for t in titles) and any("Rejection corrected" in t for t in titles)
    assert any("pended" in t for t in titles) and any("Records sent" in t for t in titles)
    assert r["submission_count"] == 2 and r["attention"] == "denial" and r["appeal"]["status"] == "drafted"
    assert "Request for reconsideration" in r["appeal"]["letter"]
    r = client.post(f"/api/encounters/{eid}/denial", json={"action": "appeal"}).json()
    assert r["appeal"]["status"] in ("upheld", "overturned") and r["attention"] is None
    r = client.post(f"/api/encounters/{eid}/autopilot").json()
    while r["attention"] == "denial":  # every CO denial gets its own decision
        client.post(f"/api/encounters/{eid}/denial", json={"action": "accept"})
        r = client.post(f"/api/encounters/{eid}/autopilot").json()
    if r["attention"] == "patient_payment":
        client.post(f"/api/encounters/{eid}/patient-payment", json={})
        r = client.post(f"/api/encounters/{eid}/autopilot").json()
    assert r["stage"] == "closed" and abs(r["balance"]) < 0.01
    t = r["totals"]
    assert t["payer_paid"] + t["patient_paid"] + t["adjustments"] == pytest.approx(t["total_charge"], abs=0.02)
