"""Claim-level analysis: deterministic findings + grounded SLM explanation.

    claim record -> rule-based findings, actions, confidence (deterministic)
                 -> fact sheet + RAG references -> local SLM narrative -> validation
                 -> (regenerate) -> (rule-based narrative fallback if the model fails validation)

The structured fields (issues, actions, confidence) never depend on the model.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import prompts
from app.ai.intent import detect_terms
from app.ai.llm_provider import GenerationParams, LLMProvider
from app.ai.postprocess import normalize_sections
from app.ai.prompts import ContextBlock
from app.ai.rag import retrieve_context
from app.ai.validators import ResponseValidator
from app.core.config import Settings
from app.models.rcm import Claim, ClaimStatus
from app.rag.base import KnowledgeRetriever
from app.services.claims_service import claim_days_in_ar, get_claim

logger = logging.getLogger(__name__)


@dataclass
class Finding:
    severity: str  # high | medium | low | info
    title: str
    detail: str


@dataclass
class ClaimFacts:
    claim: Claim
    as_of: date
    fact_sheet: str
    summary: str
    findings: list[Finding] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    confidence: float = 0.8
    retrieval_query: str = ""


# CARC category -> (explanation, recommended actions)
PLAYBOOK: dict[str, tuple[str, list[str]]] = {
    "authorization": (
        "The payer required prior authorization for this service and no valid authorization was on the claim.",
        ["Check whether an authorization was obtained but not reported; if so, submit a corrected claim with the authorization number.",
         "If none was obtained, request retroactive authorization where the payer allows it, then appeal with medical records.",
         "Add an authorization check for this payer and procedure at scheduling to prevent repeat denials."]),
    "missing_information": (
        "The claim was missing required information or contained a billing error.",
        ["Review the CARC/RARC on the remittance to identify the missing or invalid field.",
         "Correct the claim and resubmit it as a corrected claim (frequency code 7).",
         "Add a claim scrubber edit for this error."]),
    "eligibility": (
        "The payer could not confirm active coverage for the patient on the date of service.",
        ["Re-verify eligibility for the date of service (X12 270/271 or payer portal).",
         "If other coverage was active, bill the correct payer; otherwise move the balance to patient responsibility per policy.",
         "Reinforce eligibility verification at registration."]),
    "medical_necessity": (
        "The payer decided the service was not medically necessary for the reported diagnosis.",
        ["Review the payer's coverage policy (LCD/NCD for Medicare plans) against the documented diagnosis.",
         "If documentation supports necessity, appeal with clinical notes; correct the diagnosis coding if it was incomplete.",
         "For Medicare patients, obtain an ABN before services likely to be denied."]),
    "coding": (
        "The payer found a coding problem: a diagnosis/procedure mismatch, an inappropriate modifier, or a bundled service.",
        ["Have a coder review the CPT, modifier and ICD-10 combination against NCCI edits and payer policy.",
         "Correct the coding and resubmit a corrected claim, or appeal with documentation if the original coding was correct.",
         "Track recurring coding denials by provider for targeted education."]),
    "duplicate": (
        "The payer identified this as a duplicate of a claim already received.",
        ["Check the status of the original claim before taking action; do not resubmit duplicates.",
         "If the original was not paid, follow up on the original claim instead."]),
    "coordination_of_benefits": (
        "The payer indicated another plan may be primary under coordination of benefits.",
        ["Confirm the patient's coverage order and update COB information.",
         "Bill the primary payer first, then submit to this payer as secondary with the primary remittance."]),
    "timely_filing": (
        "The claim was received after the payer's timely filing limit.",
        ["Look for proof of timely filing (clearinghouse acceptance reports, prior submissions) and appeal with it.",
         "If no proof exists, the balance is generally written off and cannot be billed to the patient."]),
    "documentation": (
        "The payer needs additional documentation (records or attachments) to adjudicate the claim.",
        ["Send the requested medical records or attachments referencing the claim number.",
         "Follow up within 30 days to confirm receipt and reprocessing."]),
}


def _usd(x: float) -> str:
    return f"${x:,.2f}"


def analyze_claim_facts(db: Session, claim_id: str) -> ClaimFacts | None:
    c, patient, as_of = get_claim(db, claim_id)
    if c is None:
        return None
    findings: list[Finding] = []
    actions: list[str] = []
    confidence = 0.85
    dar = claim_days_in_ar(c, as_of)
    tf_left = c.payer.timely_filing_days - (as_of - c.service_date).days
    retrieval_query = "claim follow-up accounts receivable"

    if c.status in (ClaimStatus.DENIED, ClaimStatus.APPEALED, ClaimStatus.PARTIALLY_PAID) and c.denial_category:
        expl, acts = PLAYBOOK.get(c.denial_category, ("The payer denied the claim.", ["Review the remittance and appeal if appropriate."]))
        sev = "medium" if c.status == ClaimStatus.PARTIALLY_PAID else "high"
        findings.append(Finding(sev, f"CARC {c.denial_reason_code}: {c.denial_reason}", expl))
        retrieval_query = f"CARC {c.denial_reason_code} {c.denial_reason} {c.denial_category.replace('_', ' ')} denial"
        if c.status == ClaimStatus.APPEALED:
            appeal = max((d.appeal_date for d in c.denials if d.appeal_date), default=None)
            findings.append(Finding("info", "Appeal in progress",
                                    f"An appeal or corrected claim was submitted{f' on {appeal}' if appeal else ''} and is awaiting a decision."))
            actions.append("Follow up with the payer on the appeal status if no decision within 30-45 days.")
        elif c.balance > 0.005:
            actions.extend(acts)
        if c.payer.payer_type == "medicare" and c.status == ClaimStatus.DENIED and c.balance > 0.005:
            denied_on = max((d.denial_date for d in c.denials), default=None)
            if denied_on:
                left = 120 - (as_of - denied_on).days
                findings.append(Finding("high" if left < 30 else "medium", "Medicare redetermination deadline",
                                        f"{left} days remain of the 120-day redetermination window."))
        if c.balance <= 0.005 and c.status == ClaimStatus.DENIED:
            findings.append(Finding("info", "Balance written off", "The denied balance has been written off; no further action is pending."))
            confidence = 0.9
    elif c.status == ClaimStatus.REJECTED:
        findings.append(Finding("high", "Claim rejected before adjudication",
                                f"{c.rejection_reason}. A rejected claim was never accepted by the payer, so it must be corrected and resubmitted."))
        actions += ["Correct the rejected field and resubmit as a new original claim.",
                    "Confirm acceptance on the next 277CA acknowledgment."]
        retrieval_query = "claim rejection clearinghouse resubmit"
    elif c.status == ClaimStatus.PENDING:
        recent = db.execute(
            select(Claim.claim_date, Claim.adjudication_date)
            .where(Claim.payer_id == c.payer_id, Claim.adjudication_date.isnot(None))
            .order_by(Claim.adjudication_date.desc()).limit(300)
        ).all()
        avg_days = sum((a - s).days for s, a in recent) / len(recent) if recent else None
        age = (as_of - c.claim_date).days
        expected = f" (payer average {avg_days:.0f} days)" if avg_days else ""
        overdue = avg_days is not None and age > avg_days + 14
        findings.append(Finding("medium" if overdue else "low", "Awaiting adjudication",
                                f"Submitted {age} days ago with no payer decision yet{expected}."))
        actions.append("Check claim status with an X12 276/277 inquiry or the payer portal." if overdue
                       else "No action needed yet; monitor until the payer's normal turnaround is exceeded.")
        confidence = 0.75
        retrieval_query = "claim status inquiry AR follow-up unpaid claims"
    elif c.status == ClaimStatus.PAID:
        if c.balance > 0.005:
            findings.append(Finding("low", "Patient balance outstanding",
                                    f"Payer paid; {_usd(c.balance)} of patient responsibility remains unpaid."))
            actions.append("Send a patient statement and offer payment options.")
            retrieval_query = "patient responsibility collections deductible coinsurance"
        else:
            findings.append(Finding("info", "Claim resolved", "Paid and fully posted with a zero balance."))
            actions.append("No action required.")
            retrieval_query = "payment posting ERA"
        confidence = 0.9

    if c.requires_authorization and not c.authorization_number and c.denial_category != "authorization":
        findings.append(Finding("medium", "No authorization number on file",
                                "This service requires prior authorization for this payer but the claim carries no authorization number."))
    if c.was_rejected and c.status != ClaimStatus.REJECTED:
        findings.append(Finding("low", "Rejected on first submission", f"{c.rejection_reason}; corrected and resubmitted."))
    # Timely filing only constrains claims that still have to be (re)submitted: rejected claims and
    # denials that need a corrected claim. Pending/appealed claims were already filed on time.
    if c.balance > 0.005 and c.status in (ClaimStatus.REJECTED, ClaimStatus.DENIED):
        if tf_left < 0:
            findings.append(Finding("high", "Timely filing limit passed",
                                    f"The payer's {c.payer.timely_filing_days}-day timely filing limit passed "
                                    f"{-tf_left} days ago."))
            actions.insert(0, "Look for proof of timely filing (original submission and clearinghouse acceptance "
                              "reports); without it the balance is generally written off and cannot be billed to the patient.")
            confidence = min(confidence, 0.8)
        elif tf_left < 30:
            findings.append(Finding("high", "Timely filing risk",
                                    f"{tf_left} days remain before the payer's timely filing limit."))

    lines = [
        f"Claim {c.id} (synthetic data). Payer: {c.payer.name} ({c.payer.payer_type.replace('_', ' ')}). "
        f"Provider: {c.provider.name} ({c.provider.specialty}).",
        f"Service date {c.service_date}; submitted {c.claim_date}; adjudicated {c.adjudication_date or 'not yet'}. "
        f"Days in AR: {dar}. Submissions: {c.submission_count}.",
        f"Procedure: CPT {c.cpt_code}{f'-{c.modifier}' if c.modifier else ''} {c.cpt_description} x{c.units}; "
        f"diagnosis ICD-10 {c.icd10_code} {c.icd10_description}.",
        f"Billed {_usd(c.billed_amount)}; allowed {_usd(c.allowed_amount)}; payer paid {_usd(c.paid_amount)}; "
        f"patient responsibility {_usd(c.patient_responsibility)}; patient paid {_usd(c.patient_paid_amount)}; "
        f"contractual adjustment {_usd(c.contractual_adjustment)}; write-off {_usd(c.writeoff_amount)}; "
        f"balance {_usd(c.balance)}.",
        f"Status: {c.status.replace('_', ' ')}."
        + (f" Denial: CARC {c.denial_reason_code} - {c.denial_reason} (category: {c.denial_category.replace('_', ' ')})."
           if c.denial_reason_code else "")
        + (f" Rejection: {c.rejection_reason}." if c.rejection_reason else ""),
        f"Prior authorization required: {'yes' if c.requires_authorization else 'no'}; "
        f"authorization number on claim: {'yes' if c.authorization_number else 'none'}.",
        "Rule-based findings:", *[f"- [{f.severity}] {f.title}: {f.detail}" for f in findings],
        "Rule-based recommended actions:", *[f"- {a}" for a in actions],
    ]
    summary = (f"{c.cpt_description} (CPT {c.cpt_code}) for a synthetic patient, billed {_usd(c.billed_amount)} to "
               f"{c.payer.name}; status {c.status.replace('_', ' ')} with balance {_usd(c.balance)}.")
    return ClaimFacts(c, as_of, "\n".join(lines), summary, findings, actions, confidence, retrieval_query)


class ClaimAnalysisService:
    def __init__(self, llm: LLMProvider, settings: Settings, retriever: KnowledgeRetriever | None,
                 validator: ResponseValidator | None = None) -> None:
        self.llm, self.settings, self.retriever = llm, settings, retriever
        self.validator = validator or ResponseValidator()

    def analyze(self, db: Session, claim_id: str) -> dict | None:
        t0 = time.perf_counter()
        facts = analyze_claim_facts(db, claim_id)
        if facts is None:
            return None
        terms = detect_terms(facts.retrieval_query)
        refs = retrieve_context(self.retriever, facts.retrieval_query, k=2, terms=terms)
        blocks = [ContextBlock(i + 1, f"{r.chunk.title} - {r.chunk.section}", r.chunk.text) for i, r in enumerate(refs)]
        question = f"Analyze claim {facts.claim.id} and recommend the next action."
        messages = prompts.build_messages(question, references=blocks or None, data_context=facts.fact_sheet,
                                          format_instructions=prompts.FORMAT_CLAIM)
        params = GenerationParams(max_tokens=380, temperature=0.2, top_p=self.settings.llm_top_p,
                                  top_k=self.settings.llm_top_k, repeat_penalty=self.settings.llm_repeat_penalty)
        result = self.llm.generate(messages, params)
        ref_texts = [r.chunk.text for r in refs]
        report = self.validator.validate(result.text, question + " claim status denial payer", terms, ref_texts,
                                         facts.fact_sheet, result.finish_reason)
        regenerated, narrative, source = False, result.text, "llm"
        if not report.passed:
            regenerated = True
            messages = prompts.build_messages(question, references=blocks or None, data_context=facts.fact_sheet,
                                              format_instructions=prompts.FORMAT_CLAIM,
                                              correction=report.correction_hint())
            result = self.llm.generate(messages, GenerationParams(**{**params.__dict__, "temperature": 0.05}))
            report = self.validator.validate(result.text, question + " claim status denial payer", terms, ref_texts,
                                             facts.fact_sheet, result.finish_reason)
            narrative = result.text
            if not report.passed:
                narrative, source = _rule_based_narrative(facts), "rule_based_fallback"
        if source == "llm":
            narrative = _pin_claim_summary(narrative, facts.summary)
        c = facts.claim
        return {
            "claim_id": c.id,
            "summary": facts.summary,
            "status": c.status,
            "issues": [f.__dict__ for f in facts.findings],
            "recommended_actions": facts.actions,
            "confidence": facts.confidence,
            "confidence_label": "high" if facts.confidence >= 0.85 else "medium" if facts.confidence >= 0.7 else "low",
            "narrative": narrative,
            "narrative_source": source,
            "sources": [{"ref": i + 1, "title": r.chunk.title, "section": r.chunk.section, "document": r.chunk.document,
                         "score": round(r.score, 3), "snippet": r.chunk.text[:280]} for i, r in enumerate(refs)],
            "validation": {"passed": report.passed, "regenerated": regenerated,
                           "issues": [{"code": i.code, "severity": i.severity, "message": i.message} for i in report.issues]},
            "model": result.model,
            "usage": {"prompt_tokens": result.prompt_tokens, "completion_tokens": result.completion_tokens},
            "timings_ms": {"total": round((time.perf_counter() - t0) * 1000, 1)},
        }


def _pin_claim_summary(narrative: str, summary: str) -> str:
    """Replace the model's 'Claim summary' with the deterministic one: identifying facts
    (procedure, payer, amounts) must never come from the model."""
    text = normalize_sections(narrative)
    body = re.sub(r"\*\*Claim summary:\*\*.*?(?=\n\s*\*\*|\Z)", "", text, flags=re.S).strip()
    return f"**Claim summary:** {summary}\n\n{body}"


def _rule_based_narrative(f: ClaimFacts) -> str:
    """Deterministic narrative used only when the SLM output fails validation twice."""
    issue = next((x for x in f.findings if x.severity in ("high", "medium")), f.findings[0] if f.findings else None)
    return "\n".join([
        f"**Claim summary:** {f.summary}",
        f"**Current status:** {f.claim.status.replace('_', ' ').capitalize()}.",
        f"**Potential issue:** {issue.title + ' - ' + issue.detail if issue else 'None identified.'}",
        f"**Recommended next action:** {f.actions[0] if f.actions else 'No action required.'}",
        "_Generated from rule-based findings because the model output did not pass validation._",
    ])
