import pytest

from app.ai.postprocess import clean_answer, normalize_sections, strip_question_echo
from app.ai.validators import ResponseValidator, is_definition_question


def test_strip_question_echo():
    assert strip_question_echo("Why did our denial rate increase? Answer: it rose.", "Why did our denial rate increase?") \
        == "Answer: it rose."
    assert strip_question_echo("Answer: fine", "Something else?") == "Answer: fine"


def test_normalize_sections_bolds_labels_and_breaks_lines():
    out = normalize_sections("Answer: X rose. Key drivers: - a\n- b Recommended actions: - fix it")
    assert out.startswith("**Answer:** X rose.")
    assert "\n\n**Key drivers:**\n- a" in out
    assert "**Recommended actions:**\n- fix it" in out


def test_clean_answer_keeps_existing_bold_labels():
    text = "**Answer:** ERA is the 835.\n\n**Why it matters:** posting."
    assert clean_answer(text, "What is an ERA?") == text


def test_clean_answer_drops_echoed_reference_list():
    # Real output: the model appended the reference blocks it was given.
    text = ("**Answer:** An ERA is the 835 remittance [1].\n**Recommended action:** Post it.\n"
            "[1] ERA and EOB - Remittance Documents - What is an ERA?\nAn ERA (Electronic Remittance Advice) is ...\n"
            "[2] Curated RCM Q&A - RCM terminology > What is an ERA?")
    out = clean_answer(text, "What is an ERA?")
    assert out.endswith("**Recommended action:** Post it.")
    assert "remittance [1]." in out


@pytest.mark.parametrize("question, terms, expected", [
    ("What is an ERA?", ["era"], True),
    ("Explain payment posting.", ["payment_posting"], True),
    ("ERA vs EOB", ["era", "eob"], True),
    ("What is the difference between a claim rejection and denial?", ["denial", "rejection"], True),
    ("What are the major causes of denials?", ["denial"], False),
    ("Why might a claim be denied?", ["denial"], False),
    ("Which payer has the highest denial rate?", ["denial_rate"], False),
])
def test_is_definition_question(question, terms, expected):
    assert is_definition_question(question, terms) is expected


def test_direction_mismatch_detected():
    data = "KEY FINDINGS:\n1. The denial rate decreased: 12.6% -> 12.0%.\nDirection: the denial rate decreased."
    rep = ResponseValidator().validate("**Answer:** The denial rate increased from 12.6% to 12.0% this quarter.",
                                       "Why did our denial rate increase?", ["denial_rate"], data_text=data)
    assert any(i.code == "direction_mismatch" for i in rep.issues)


def test_direction_consistent_passes():
    data = "Direction: the denial rate increased."
    rep = ResponseValidator().validate("**Answer:** The denial rate increased from 11.7% to 12.8%, driven by Cobalt.",
                                       "Why did our denial rate increase?", ["denial_rate"],
                                       data_text=data + " 11.7% 12.8% Cobalt")
    assert not any(i.code == "direction_mismatch" for i in rep.issues)
