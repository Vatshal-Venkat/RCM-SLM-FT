from app.ai.validators import ResponseValidator

V = ResponseValidator()


def codes(report):
    return {i.code for i in report.issues if i.severity == "error"}


def test_hallucinated_era_expansions_are_rejected():
    # Real outputs of the un-grounded fine-tuned model.
    for bad in [
        "An ERA is an Event-Related Audit. It refers to a specific billing event used for audits.",
        "An **ERA** in Revenue Cycle Management stands for **Electronic Retrieval Agreement**.",
        "ERA stands for Electronic Revenue Attribution, the process of attributing payments.",
    ]:
        rep = V.validate(bad, "What is an ERA?", ["era"])
        assert not rep.passed, bad
        assert codes(rep) & {"incorrect_expansion", "incorrect_definition", "missing_core_concept"}


def test_correct_era_definition_passes():
    good = ("**Answer:** An ERA (Electronic Remittance Advice) is the electronic X12 835 transaction a payer "
            "sends to a provider explaining payment and adjustments for adjudicated claims.")
    rep = V.validate(good, "What is an ERA?", ["era"])
    assert rep.passed, rep.issues


def test_wrong_days_in_ar_formula_detected():
    bad = "Days in AR is calculated as total charges divided by total payments for the period."
    rep = V.validate(bad, "How is Days in AR calculated?", ["days_in_ar"])
    assert "incorrect_formula" in codes(rep)


def test_correct_days_in_ar_formula_passes():
    good = ("Days in AR = Total accounts receivable / Average daily gross charges. It measures how many days "
            "it takes to collect payment.")
    rep = V.validate(good, "How is Days in AR calculated?", ["days_in_ar"])
    assert "incorrect_formula" not in codes(rep)


def test_rejection_must_not_be_appealed():
    bad = "A claim rejection happens before adjudication at the clearinghouse. You should appeal the rejection with the payer."
    rep = V.validate(bad, "What is a claim rejection?", ["rejection"])
    assert "incorrect_definition" in codes(rep)


def test_phi_detected():
    rep = V.validate("The patient John's SSN is 123-45-6789 and the claim was denied by the payer.",
                     "why was the claim denied", ["denial"])
    assert "phi_detected" in codes(rep)


def test_repetition_detected():
    sentence = "Payment posting records payments and adjustments against patient accounts in the system. "
    rep = V.validate(sentence * 4, "Explain payment posting", ["payment_posting"])
    assert "repetition" in codes(rep)


def test_unsupported_numbers_are_errors_when_data_given():
    rep = V.validate("Our denial rate is 23.4% this quarter, driven by Payer A.",
                     "What is our denial rate?", ["denial_rate"], data_text="denial_rate_pct: 11.8")
    assert "unsupported_numbers" in codes(rep)


def test_numbers_from_data_are_supported():
    rep = V.validate("Our denial rate is 11.8% this quarter based on denied claims over total claims.",
                     "What is our denial rate?", ["denial_rate"], data_text="denial_rate_pct: 11.8")
    assert "unsupported_numbers" not in codes(rep)


def test_irrelevant_answer_detected():
    rep = V.validate("Bananas are rich in potassium and make a great snack for athletes.",
                     "What is prior authorization?", ["prior_authorization"])
    assert "irrelevant" in codes(rep)


def test_invalid_citation_flagged():
    rep = V.validate("An EOB (Explanation of Benefits) is a statement to the patient [3].",
                     "What is an EOB?", ["eob"], reference_texts=["An EOB is a statement"])
    assert any(i.code == "invalid_citation" for i in rep.issues)
