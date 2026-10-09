"""The RAG layer that compensates for known fine-tuning gaps (see training/README.md):
invented identifiers, generic claim answers, and thin knowledge coverage."""

import asyncio
import json
from collections.abc import Iterator

import pytest

from app.ai.intent import detect_terms
from app.ai.llm_provider import ChatMessage, GenerationParams, LLMProvider, LLMResult, ModelInfo
from app.ai.rag import retrieve_context, select_context
from app.ai.validators import ID_REDACTION, ResponseValidator, redact_identifiers, unsupported_identifiers
from app.core.config import REPO_ROOT, Settings
from app.rag.base import Chunk, RetrievedChunk
from app.rag.loaders import load_document
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService, DataContext

V = ResponseValidator()


def _hit(doc: str, section: str, score: float, text: str = "reference text", category: str | None = None) -> RetrievedChunk:
    return RetrievedChunk(Chunk(f"{doc}-{section}", doc, doc, section, text, {"category": category}), score)


class FakeRetriever:
    def __init__(self, hits: list[RetrievedChunk]) -> None:
        self.hits, self.queries = hits, []

    def retrieve(self, query: str, k: int = 4) -> list[RetrievedChunk]:
        self.queries.append(query)
        return self.hits[:k]

    def is_ready(self) -> bool:
        return True


class ScriptedLLM(LLMProvider):
    def __init__(self, *replies: str) -> None:
        self.replies, self.calls = list(replies), []

    def load(self) -> None: ...

    def is_ready(self) -> bool:
        return True

    def info(self) -> ModelInfo:
        return ModelInfo("fake", "fake", True)

    def generate(self, messages: list[ChatMessage], params: GenerationParams) -> LLMResult:
        self.calls.append(messages)
        text = self.replies[min(len(self.calls), len(self.replies)) - 1]
        return LLMResult(text, 0, 0, "stop", 0.0, "fake")

    def stream(self, messages: list[ChatMessage], params: GenerationParams) -> Iterator[str]:
        yield self.generate(messages, params).text

    def count_tokens(self, text: str) -> int:
        return len(text.split())


# --------------------------------------------------------------------------- identifiers
def test_invented_claim_number_is_rejected():
    # The exact pattern the claim_summary training rows teach.
    rep = V.validate("This is an inpatient claim. The claim identifier is 196191176997272 for the stay.",
                     "Summarize this inpatient claim", [])
    assert any(i.code == "unsupported_identifier" and i.severity == "error" for i in rep.issues)
    assert not any(i.code == "unsupported_numbers" for i in rep.issues), "identifiers are reported once"


@pytest.mark.parametrize("answer", [
    "Claim CLM-004521 was denied for missing authorization by the payer.",
    "The payer PYR-ZZZ denied the claim for missing authorization.",
    "The claim for <PROVIDER_ID> was denied for missing authorization.",
])
def test_identifiers_absent_from_sources_are_rejected(answer):
    rep = V.validate(answer, "Why was claim CLM-001234 denied?", ["denial"],
                     data_text="Claim CLM-001234. Payer PYR-MCR. Denial: CARC 197.")
    assert any(i.code == "unsupported_identifier" for i in rep.issues), rep.issues


def test_identifiers_from_question_or_data_are_allowed():
    rep = V.validate("Claim CLM-001234 from PYR-MCR was denied with CARC 197 for missing authorization.",
                     "Why was claim CLM 001234 denied?", ["denial"],
                     data_text="Claim CLM-001234. Payer PYR-MCR. Denial: CARC 197 authorization.")
    assert not any(i.code == "unsupported_identifier" for i in rep.issues), rep.issues


def test_redaction_keeps_supported_identifiers():
    out = redact_identifiers("CLM-001234 is a duplicate of CLM-009999 (claim 196191176997272).", ["Claim CLM-001234"])
    assert out == f"CLM-001234 is a duplicate of {ID_REDACTION} (claim {ID_REDACTION})."
    assert unsupported_identifiers("Paid $1,234,567,890 on 20090314.", []) == []


def test_relevance_tolerates_plural_and_tense():
    rep = V.validate("Rejections are fixed and resubmitted; denials are appealed or corrected after adjudication.",
                     "Compare rejection and denial", [])
    assert not any(i.code == "irrelevant" for i in rep.issues)


# --------------------------------------------------------------------------- context selection
def test_curated_qa_limited_to_one_chunk_in_context():
    hits = [_hit("curated_qa.md", "q1", 0.99, category="curated_qa"),
            _hit("curated_qa.md", "q2", 0.98, category="curated_qa"),
            _hit("era_eob.md", "ERA", 0.90), _hit("payment_posting.md", "ERA posting", 0.80)]
    chosen = select_context(hits, k=3)
    assert [h.chunk.section for h in chosen] == ["q1", "ERA", "ERA posting"]


def test_term_definition_comes_from_reference_document():
    retriever = FakeRetriever([_hit("curated_qa.md", "What is an ERA?", 0.99, category="curated_qa"),
                               _hit("era_eob.md", "What is an ERA?", 0.95)])
    refs = retrieve_context(retriever, "What is an ERA?", k=2, terms=["era"])
    assert refs[0].chunk.document == "era_eob.md"


# --------------------------------------------------------------------------- chat pipeline
CLAIM_FACTS = ("Claim CLM-001234 (synthetic data). Payer: Northwind Health.\n"
               "Status: denied. Denial: CARC 197 - Precertification/authorization absent (category: authorization).")


class ClaimProvider:
    def build(self, intent, question):
        return DataContext(CLAIM_FACTS, {"type": "claim", "found": True, "claim_id": "CLM-001234"},
                           retrieval_query="CARC 197 Precertification/authorization absent authorization denial")


def _service(llm, retriever, data_provider=None):
    return ChatService(llm, Settings(_env_file=None), retriever=retriever, data_provider=data_provider)


def test_claim_question_retrieves_on_claim_facts():
    retriever = FakeRetriever([_hit("prior_authorization.md", "Retro authorization", 0.9,
                                    "Request retroactive authorization and appeal a CARC 197 denial.")])
    llm = ScriptedLLM("**Claim summary:** Claim CLM-001234 was denied with CARC 197 because authorization was "
                      "absent [1].\n**Recommended next action:** Request retroactive authorization and appeal.")
    resp = asyncio.run(_service(llm, retriever, ClaimProvider()).answer(
        ChatRequest(message="Why was claim CLM-001234 denied?")))
    assert retriever.queries[0].startswith("CARC 197")
    assert resp.validation.passed, resp.validation.issues


def test_identifier_invented_twice_is_masked():
    era = _hit("era_eob.md", "What is an ERA?", 0.95,
               "An ERA (Electronic Remittance Advice) is the X12 835 transaction a payer sends to a provider.")
    bad = ("**Answer:** An ERA (Electronic Remittance Advice) is the X12 835 remittance a payer sends to a "
           "provider [1]. For example, the claim identifier is 196191176997272.")
    llm = ScriptedLLM(bad, bad)
    resp = asyncio.run(_service(llm, FakeRetriever([era])).answer(ChatRequest(message="What is an ERA?")))
    assert "196191176997272" not in resp.answer and ID_REDACTION in resp.answer
    assert resp.validation.passed and resp.validation.regenerated
    assert any(i.code == "unsupported_identifier" and i.severity == "warning" for i in resp.validation.issues)


# --------------------------------------------------------------------------- curated Q&A corpus
CURATED = REPO_ROOT / "knowledge" / "curated_qa.md"
HOLDOUT = [REPO_ROOT / "training" / "datasets" / "v2_1" / f"{s}.jsonl" for s in ("validation", "test")]


@pytest.mark.skipif(not CURATED.is_file() or not all(p.is_file() for p in HOLDOUT),
                    reason="curated Q&A or training splits not present")
def test_curated_qa_is_clean():
    doc = load_document(CURATED)
    assert doc.metadata["category"] == "curated_qa"
    held_out = {json.loads(line)["instruction"].strip() for p in HOLDOUT for line in p.open(encoding="utf-8") if line.strip()}
    questions = [(s.heading or "").split(" > ")[-1] for s in doc.sections]
    assert questions and not set(questions) & held_out, "validation/test questions leaked into the RAG corpus"
    for q, s in zip(questions, doc.sections):
        assert V.validate(s.text, q, detect_terms(q)).passed, q
