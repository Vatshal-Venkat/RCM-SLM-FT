"""Chat answers about one claim: claim-specific format, no other payer's rules, and a rule-based
answer instead of a model answer that failed validation twice."""

import asyncio

from app.schemas.chat import ChatRequest
from app.services.claim_analysis import analyze_claim_facts
from app.services.copilot_context import AnalyticsContextProvider
from tests.test_rag_layer import FakeRetriever, ScriptedLLM, _service


def _denied(seeded_db, **kw):
    return next(c for c in seeded_db["claims"] if c["status"] == "denied" and all(c[k] == v for k, v in kw.items()))


def _ask(seeded_db, llm, question):
    svc = _service(llm, FakeRetriever([]), data_provider=AnalyticsContextProvider())
    return asyncio.run(svc.answer(ChatRequest(message=question)))


def test_claim_question_uses_claim_format_and_payer_rules(seeded_db):
    claim = _denied(seeded_db)
    llm = ScriptedLLM(f"**Answer:** Claim {claim['id']} was denied with CARC {claim['denial_reason_code']}.")
    _ask(seeded_db, llm, f"Why was claim {claim['id']} denied?")
    system, user = llm.calls[0][0].content, llm.calls[0][-1].content
    assert "**Details:**" in system and "Key drivers" not in system
    assert "timely filing limit is" in user and "Apply only this payer's rules" in user


def test_other_payer_rule_is_rejected_then_rule_based_answer_shown(seeded_db):
    claim = _denied(seeded_db)
    facts_payer = claim["payer_id"]
    other = "Medicare" if facts_payer != "PYR-MCR" else "Medicaid"
    wrong = (f"**Answer:** The claim was denied. {other} requires claims to be filed within 12 months, "
             "and the denial rate was 85%.")
    resp = _ask(seeded_db, ScriptedLLM(wrong, wrong), f"Why was claim {claim['id']} denied?")
    assert resp.validation.passed and resp.validation.regenerated
    codes = {i.code for i in resp.validation.issues}
    assert {"draft_off_record_entity", "rule_based_fallback"} <= codes
    assert other not in resp.answer and "85%" not in resp.answer
    assert f"CARC {claim['denial_reason_code']}" in resp.answer and "rule-based findings" in resp.answer


def test_valid_claim_answer_is_kept(seeded_db):
    claim = _denied(seeded_db)
    good = f"**Answer:** Claim {claim['id']} was denied with CARC {claim['denial_reason_code']}."
    resp = _ask(seeded_db, ScriptedLLM(good), f"Why was claim {claim['id']} denied?")
    assert resp.answer == good and not resp.validation.regenerated


def test_written_off_denial_still_has_actions(db, seeded_db):
    claim = next((c for c in seeded_db["claims"] if c["status"] == "denied" and c["balance"] == 0), None)
    if claim is None:
        return
    actions = analyze_claim_facts(db, claim["id"]).actions
    assert actions and actions[0].startswith("No recovery action is pending")


def test_on_time_claim_denied_for_timely_filing_is_flagged_for_appeal(db, seeded_db):
    from datetime import date

    for c in seeded_db["claims"]:
        if c["denial_reason_code"] == "29" and c["status"] == "denied" and c["balance"] > 0:
            facts = analyze_claim_facts(db, c["id"])
            lag = (date.fromisoformat(str(c["claim_date"])) - date.fromisoformat(str(c["service_date"]))).days
            if lag <= facts.claim.payer.timely_filing_days:
                assert facts.findings[1].title == "Original submission was on time"
                assert facts.actions[0].startswith("Appeal the CARC 29 denial")
                assert "received after its timely filing limit" in facts.findings[0].detail


def test_timely_filing_action_not_duplicated(db, seeded_db):
    for c in seeded_db["claims"]:
        if c["status"] == "denied" and c["balance"] > 0:
            actions = analyze_claim_facts(db, c["id"]).actions
            assert len(actions) == len(set(actions))
            assert sum("proof of timely filing" in a for a in actions) <= 1
