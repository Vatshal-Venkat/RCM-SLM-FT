import pytest

from app.ai.intent import Intent, classify, detect_terms


@pytest.mark.parametrize(
    "question, intent",
    [
        ("What is an ERA?", Intent.RCM_KNOWLEDGE),
        ("Explain the difference between an ERA and an EOB.", Intent.RCM_KNOWLEDGE),
        ("How is First-Pass Resolution Rate calculated?", Intent.RCM_KNOWLEDGE),
        ("Why might a claim be denied?", Intent.RCM_KNOWLEDGE),
        ("What is the difference between a claim rejection and denial?", Intent.RCM_KNOWLEDGE),
        ("Which payer has the highest denial rate?", Intent.KPI_ANALYTICS),
        ("Why did our denial rate increase?", Intent.KPI_ANALYTICS),
        ("What is causing our AR to increase?", Intent.KPI_ANALYTICS),
        ("Which claims should we prioritize?", Intent.KPI_ANALYTICS),
        ("Analyze claim CLM-000123", Intent.CLAIM_SPECIFIC),
        ("hello", Intent.GREETING),
        ("Give me a banana bread recipe", Intent.OUT_OF_SCOPE),
    ],
)
def test_classify(question, intent):
    assert classify(question).intent == intent


def test_claim_id_entity_is_normalised():
    r = classify("why was claim clm 004512 denied?")
    assert r.entities["claim_ids"] == ["CLM-004512"]
    assert "denial" in r.terms


@pytest.mark.parametrize(
    "text, expected",
    [
        ("What is an ERA in Revenue Cycle Management?", {"era"}),
        ("ERA vs EOB", {"era", "eob"}),
        ("What is Days in AR?", {"days_in_ar"}),
        ("How is FPRR calculated?", {"first_pass_resolution"}),
        ("what's our denial rate", {"denial_rate"}),
        ("denials and the denial rate", {"denial", "denial_rate"}),
        ("Do we need prior auth for an MRI?", {"prior_authorization"}),
        ("Explain cash posting", {"payment_posting"}),
    ],
)
def test_detect_terms(text, expected):
    assert set(detect_terms(text)) == expected


def test_era_not_matched_inside_words():
    assert "era" not in detect_terms("We operate several clinics and generate reports")
