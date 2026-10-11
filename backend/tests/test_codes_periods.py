"""Code lookup (CARC / group / RARC / modifier), named reporting periods, and routing of general
KPI questions. Each case below is a question the live model previously answered wrongly."""

import asyncio
from datetime import date

import pytest

from app.ai.codes import detect_codes, load_code_rules
from app.ai.intent import Intent, classify
from app.ai.periods import parse_period
from app.ai.validators import ResponseValidator
from app.schemas.chat import ChatRequest
from app.services.copilot_context import AnalyticsContextProvider
from tests.test_rag_layer import FakeRetriever, ScriptedLLM, _hit, _service

V = ResponseValidator()
AS_OF = date(2026, 10, 6)


# --------------------------------------------------------------------------- code detection
@pytest.mark.parametrize("text, expected", [
    ("What does CARC CO-45 mean?", ["carc_45", "group_co"]),
    ("What does denial code CO-16 mean?", ["carc_16", "group_co"]),
    ("What does CARC 97 mean?", ["carc_97"]),
    ("What is denial code 197?", ["carc_197"]),
    ("What does PR-1 mean on a remittance?", ["carc_1", "group_pr"]),
    ("What is the difference between group codes CO and PR?", ["group_co", "group_pr"]),
    ("What does CPT modifier 25 mean?", ["modifier_25"]),
    ("When do I use modifiers 59 and XS?", ["modifier_59", "modifier_xs"]),
    ("Do we need the GA modifier?", ["modifier_ga"]),
    ("Explain reason codes 16, 29 and 50", ["carc_16", "carc_29", "carc_50"]),
    ("RARC N30 vs M51", ["rarc_n30", "rarc_m51"]),
])
def test_detect_codes(text, expected):
    assert detect_codes(text) == expected


@pytest.mark.parametrize("text", [
    "What is a CARC?",                     # the concept, not a code: handled by validated_terms.yaml
    "Why did we get 50 denials last month?",  # a count, not CARC 50
    "Is ICD-10 M54.50 billable?",          # an ICD-10 code, not RARC M54
    "What is co-insurance?",
])
def test_detect_codes_ignores_non_codes(text):
    assert detect_codes(text) == []


def test_code_definition_carries_official_description_and_group():
    rule = load_code_rules()["carc_45"]
    assert "fee schedule" in rule.definition and "CO-45" in rule.definition and rule.kind == "code"


def test_code_answer_missing_core_concept_is_rejected():
    # The live model's answer to "What does CARC CO-45 mean?" before code lookup existed.
    wrong = ("CARC CO-45 is a claim adjustment group code indicating a contractual obligation. It is typically "
             "associated with overcharges or errors in billing.")
    rep = V.validate(wrong, "What does CARC CO-45 mean?", ["carc", "carc_45", "group_co"])
    assert any(i.code == "missing_core_concept" and i.term == "carc_45" for i in rep.issues)
    right = "CARC 45 means the charge exceeds the fee schedule or maximum allowable; CO means contractual obligation."
    assert V.validate(right, "What does CARC CO-45 mean?", ["carc", "carc_45", "group_co"]).passed


def test_code_concept_not_required_in_data_answers():
    rep = V.validate("CARC 197 denials rose from 47 to 75.", "Why did CO-197 denials increase?", ["carc_197"],
                     data_text="CARC 197: 47 -> 75 denials.")
    assert not any(i.code == "missing_core_concept" for i in rep.issues)


def test_code_definition_is_pinned_first_and_cited_as_source():
    llm = ScriptedLLM("**Answer:** CARC 16 means the claim lacks information or has a billing error [1].")
    svc = _service(llm, FakeRetriever([_hit("denials_and_rejections.md", "Codes", 0.9)]))
    resp = asyncio.run(svc.answer(ChatRequest(message="What does denial code CO-16 mean?")))
    prompt = llm.calls[0][-1].content
    assert prompt.index("[1] Code reference: CARC 16") < prompt.index("denials_and_rejections")
    assert [s.document for s in resp.sources][:2] == ["code_reference.yaml", "code_reference.yaml"]
    assert [s.ref for s in resp.sources] == list(range(1, len(resp.sources) + 1))
    assert resp.validation.passed and not resp.validation.regenerated


def test_code_contradicted_twice_falls_back_to_code_reference():
    wrong = "**Answer:** CARC 29 is a code used on remittances to explain adjustments."
    svc = _service(ScriptedLLM(wrong, wrong), FakeRetriever([]))
    resp = asyncio.run(svc.answer(ChatRequest(message="What does CARC 29 mean?")))
    assert resp.validation.regenerated
    assert "The time limit for filing has expired" in resp.answer


# --------------------------------------------------------------------------- periods
@pytest.mark.parametrize("text, start, end, label", [
    ("denial rate in September 2026", date(2026, 9, 1), date(2026, 9, 30), "September 2026"),
    ("denial rate in September", date(2026, 9, 1), date(2026, 9, 30), "September 2026"),
    ("November's denial rate", date(2025, 11, 1), date(2025, 11, 30), "November 2025"),
    ("Sep 2026", date(2026, 9, 1), date(2026, 9, 30), "September 2026"),
    ("Q2 2026", date(2026, 4, 1), date(2026, 6, 30), "Q2 2026"),
    ("third quarter", date(2026, 7, 1), date(2026, 9, 30), "Q3 2026"),
    ("from May to July 2026", date(2026, 5, 1), date(2026, 7, 31), "May 2026 to July 2026"),
    ("between November and January", date(2025, 11, 1), date(2026, 1, 31), "November 2025 to January 2026"),
    ("in 2025", date(2025, 1, 1), date(2025, 12, 31), "2025"),
    ("2026-05-01 to 2026-06-30", date(2026, 5, 1), date(2026, 6, 30), "2026-05-01 to 2026-06-30"),
])
def test_parse_period(text, start, end, label):
    p = parse_period(text, AS_OF)
    assert (p.start, p.end, p.label, p.partial) == (start, end, label, False)


def test_period_in_progress_is_clipped_to_as_of():
    p = parse_period("denial rate in October", AS_OF)
    assert (p.start, p.end, p.partial) == (date(2026, 10, 1), AS_OF, True)


@pytest.mark.parametrize("text", ["What may cause denials?", "last 30 days", "this quarter", "What is CARC 29?"])
def test_no_named_period(text):
    assert parse_period(text, AS_OF) is None


def test_named_month_uses_that_month_not_the_default_window(seeded_db):
    q = "What was our denial rate in September 2026?"
    ctx = AnalyticsContextProvider().build(classify(q), q)
    assert ctx.payload["type"] == "kpi_summary"
    assert ctx.payload["period"] == {"start": "2026-09-01", "end": "2026-09-30"}
    assert ctx.text.startswith("Requested period: September 2026")


def test_named_period_with_no_claims_says_so(seeded_db):
    q = "What was our denial rate in March 2020?"
    ctx = AnalyticsContextProvider().build(classify(q), q)
    assert "No claims were submitted in this period" in ctx.text


# --------------------------------------------------------------------------- routing
@pytest.mark.parametrize("question, intent", [
    ("First-Pass Resolution Rate decreased from 90% to 75%. What should an RCM analyst investigate?",
     Intent.RCM_KNOWLEDGE),
    ("What does an increase in old accounts receivable generally suggest?", Intent.RCM_KNOWLEDGE),
    ("What does it mean if Days in AR increases?", Intent.RCM_KNOWLEDGE),
    ("What should we do if our denial rate increases?", Intent.KPI_ANALYTICS),
    ("Denial rate in September 2026?", Intent.KPI_ANALYTICS),
    ("Which payer had the highest denial rate in Q2?", Intent.KPI_ANALYTICS),
    ("What does CARC 97 mean?", Intent.RCM_KNOWLEDGE),
])
def test_general_kpi_questions_are_not_routed_to_our_data(question, intent):
    assert classify(question).intent == intent
