import pytest

from app.ai.intent import classify
from app.ai.validators import ResponseValidator
from app.services.claim_analysis import analyze_claim_facts
from app.services.copilot_context import AnalyticsContextProvider, detect_entities, detect_window_days


@pytest.mark.parametrize(
    "question, expected_type",
    [
        ("Why did our denial rate increase?", "denial_drivers"),
        ("Which payer has the highest denial rate?", "ranking"),
        ("Which provider has the lowest clean claim rate?", "ranking"),
        ("What are the major causes of denials?", "denial_causes"),
        ("Which claims should we prioritize?", "prioritization"),
        ("What is causing our AR to increase?", "ar_drivers"),
        ("How are we doing this quarter?", "kpi_summary"),
    ],
)
def test_copilot_routes_to_deterministic_insight(seeded_db, question, expected_type):
    ctx = AnalyticsContextProvider().build(classify(question), question)
    assert ctx is not None and ctx.payload["type"] == expected_type
    assert ctx.text.strip()


def test_payer_ranking_is_sorted_and_quotes_exact_rates(seeded_db):
    ctx = AnalyticsContextProvider().build(classify("Which payer has the highest denial rate?"),
                                           "Which payer has the highest denial rate?")
    rates = [r["denial_rate"] for r in ctx.payload["rows"]]
    assert rates == sorted(rates, reverse=True)
    assert f"{rates[0]:.1f}%" in ctx.text


def test_denial_driver_contributions_sum_to_change(seeded_db):
    ctx = AnalyticsContextProvider().build(classify("Why did our denial rate increase?"), "Why did our denial rate increase?")
    p = ctx.payload
    total = sum(r["contribution_pts"] for r in p["by_payer"])
    assert abs(total - (p["denial_rate_now"] - p["denial_rate_before"])) < 0.2


def test_claim_specific_question_uses_claim_facts(seeded_db):
    denied = next(c for c in seeded_db["claims"] if c["status"] == "denied")
    q = f"Why was claim {denied['id']} denied?"
    ctx = AnalyticsContextProvider().build(classify(q), q)
    assert ctx.payload["found"] and denied["id"] in ctx.text and denied["denial_reason_code"] in ctx.text


def test_claim_facts_findings_and_actions(db, seeded_db):
    denied = next(c for c in seeded_db["claims"] if c["status"] == "denied" and c["balance"] > 0)
    facts = analyze_claim_facts(db, denied["id"])
    assert facts.findings[0].severity == "high"
    assert facts.actions, "open denial must have recommended actions"
    paid = next(c for c in seeded_db["claims"] if c["status"] == "paid" and c["balance"] == 0)
    assert analyze_claim_facts(db, paid["id"]).actions == ["No action required."]
    assert analyze_claim_facts(db, "CLM-999999") is None


def test_pending_claim_has_no_timely_filing_finding(db, seeded_db):
    pending = next(c for c in seeded_db["claims"] if c["status"] == "pending")
    titles = [f.title for f in analyze_claim_facts(db, pending["id"]).findings]
    assert not any("timely filing" in t.lower() for t in titles)


def test_pinned_claim_summary_replaces_model_summary():
    from app.services.claim_analysis import _pin_claim_summary

    out = _pin_claim_summary("**Claim summary:** An office visit (wrong).\n\n**Current status:** Denied.",
                             "MRI lumbar spine (CPT 72148) billed $1,500.00.")
    assert out.startswith("**Claim summary:** MRI lumbar spine (CPT 72148)")
    assert "office visit" not in out and "**Current status:** Denied." in out


def test_entity_and_window_detection():
    assert detect_entities("denials from Cobalt at Lakeside Dermatology") == (("PYR-COB",), ("PRV-07",))
    assert detect_entities("medicare advantage plans")[0] == ("PYR-LSH",)
    assert detect_window_days("last 6 months") == 180
    assert detect_window_days("this quarter") == 90
    assert detect_window_days("anything") == 90


@pytest.mark.parametrize("answer", [
    "Cobalt's denial rate is 29.8%, up from 13.1%.",
    "Cobalt's denial rate is about 30%.",
    "Outstanding AR is $652,062.",
    "Outstanding AR is roughly $652K.",
])
def test_number_tolerance_accepts_rounded_quotes(answer):
    data = "Cobalt denial rate 29.8% (before 13.1%). Outstanding AR: $652,062."
    rep = ResponseValidator().validate(answer, "Which payer has the highest denial rate?", [], data_text=data)
    assert not any(i.code == "unsupported_numbers" for i in rep.issues), rep.issues


def test_number_tolerance_rejects_invented_figures():
    data = "Cobalt denial rate 29.8% (before 13.1%). Outstanding AR: $652,062."
    rep = ResponseValidator().validate("Cobalt's denial rate is 41.5% and AR is $910,000.",
                                       "Which payer has the highest denial rate?", [], data_text=data)
    assert any(i.code == "unsupported_numbers" and i.severity == "error" for i in rep.issues)
