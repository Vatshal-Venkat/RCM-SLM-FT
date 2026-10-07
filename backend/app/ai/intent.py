"""Deterministic query intent classification.

A rule-based router is used instead of the SLM because it is instant, explainable and cannot
hallucinate a route. Each intent decides which grounding sources the pipeline consults:

  rcm_knowledge   -> RAG over the RCM knowledge base
  kpi_analytics   -> deterministic SQL/analytics + RAG for KPI definitions
  claim_specific  -> claim record lookup + RAG
  data_query      -> listing/filtering claims (database only)
  greeting        -> no grounding needed
  out_of_scope    -> polite refusal, no model call
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum

from app.ai.validators import contains_phrase, load_term_rules, term_forms


class Intent(str, Enum):
    RCM_KNOWLEDGE = "rcm_knowledge"
    KPI_ANALYTICS = "kpi_analytics"
    CLAIM_SPECIFIC = "claim_specific"
    DATA_QUERY = "data_query"
    GREETING = "greeting"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass
class IntentResult:
    intent: Intent
    confidence: float
    matched: list[str] = field(default_factory=list)
    entities: dict[str, list[str]] = field(default_factory=dict)
    # Critical RCM terms detected in the query (used by the validator).
    terms: list[str] = field(default_factory=list)


CLAIM_ID_RE = re.compile(r"\b(?:CLM|CLAIM)[-_ ]?\d{4,10}\b", re.IGNORECASE)

# Generic word forms that should also flag the denial/rejection terms in questions
# ("why was this claim denied?"), in addition to the aliases in validated_terms.yaml.
_EXTRA_FORMS = {"denial": ["denied", "deny", "denies"], "rejection": ["rejected", "reject", "rejects"]}

_RCM_VOCAB = [
    "rcm", "revenue cycle", "claim", "claims", "payer", "payor", "billing", "coding", "cpt", "icd", "hcpcs",
    "modifier", "remittance", "adjudication", "reimbursement", "copay", "coinsurance", "deductible",
    "allowed amount", "write-off", "write off", "adjustment", "appeal", "clearinghouse", "837", "ub-04",
    "cms-1500", "eligibility", "credentialing", "charge capture", "accounts receivable", "a/r", "ar ",
    "underpayment", "timely filing", "coordination of benefits", "cob", "medical necessity", "scrubber",
    "superbill", "npi", "edi", "patient responsibility", "self-pay", "collections", "posting", "kpi",
]

_ANALYTICS_PATTERNS = [
    r"\bour\b", r"\bwe\b", r"\bwhich (payer|payor|provider|claims?)\b", r"\bhighest\b", r"\blowest\b",
    r"\btop \d+\b", r"\btrend", r"\bincreas", r"\bdecreas", r"\bwhy did\b", r"\bhow many\b",
    r"\btotal\b", r"\baverage\b", r"\bthis (month|quarter|year)\b", r"\blast (month|quarter|year)\b",
    r"\bprioriti[sz]e\b", r"\bbreakdown\b", r"\bcompare\b.*\b(payer|provider)s?\b", r"\bmajor causes\b",
    r"\bwhat is (causing|driving)\b", r"\bcurrent\b.*\brate\b", r"\bperformance\b",
]

_DATA_QUERY_PATTERNS = [r"\b(list|show|find|get)\b.*\bclaims?\b", r"\bclaims? (with|for|from|over|above|below)\b"]

_GREETING_RE = re.compile(r"^\s*(hi|hello|hey|good (morning|afternoon|evening)|thanks|thank you)\b[\s!.,]*$", re.I)

_OFF_TOPIC_HINTS = [
    "recipe", "weather", "football", "cricket", "movie", "song", "poem", "joke", "stock price", "bitcoin",
    "write code", "python script", "javascript", "translate",
]


def _contains(text: str, phrase: str) -> bool:
    return contains_phrase(text, phrase)


def detect_terms(text: str) -> list[str]:
    """Critical RCM terms (keys of validated_terms.yaml) mentioned in the text."""
    t = text.lower()
    found = []
    for key, rule in load_term_rules().items():
        forms = term_forms(rule) + _EXTRA_FORMS.get(key, [])
        if any(_contains(t, f) for f in forms):
            found.append(key)
    # A specific KPI term subsumes the generic one ("denial rate" is not a question about denials).
    if "denial_rate" in found and "denial" in found and not re.search(r"\bdenials?\b(?!\s+rate)", t):
        found.remove("denial")
    if "days_in_ar" in found and "ar" in found:
        found.remove("ar")
    return found


def classify(query: str) -> IntentResult:
    q = query.strip()
    ql = q.lower()
    terms = detect_terms(q)
    claim_ids = [m.upper().replace(" ", "-").replace("_", "-") for m in CLAIM_ID_RE.findall(q)]
    entities = {"claim_ids": claim_ids} if claim_ids else {}

    if _GREETING_RE.match(q):
        return IntentResult(Intent.GREETING, 0.95, ["greeting"], entities, terms)

    vocab_hits = [w for w in _RCM_VOCAB if _contains(ql, w.strip())]
    is_rcm = bool(terms or vocab_hits or claim_ids)

    if claim_ids:
        return IntentResult(Intent.CLAIM_SPECIFIC, 0.95, ["claim_id"], entities, terms)

    analytics_hits = [p for p in _ANALYTICS_PATTERNS if re.search(p, ql)]
    data_hits = [p for p in _DATA_QUERY_PATTERNS if re.search(p, ql)]

    if is_rcm and data_hits and not analytics_hits:
        return IntentResult(Intent.DATA_QUERY, 0.75, data_hits, entities, terms)
    # Analytics needs both an RCM subject and an "about our data" signal; a bare definition
    # question ("what is the denial rate?") matches no analytics pattern and stays knowledge.
    if is_rcm and analytics_hits:
        conf = min(0.95, 0.6 + 0.1 * len(analytics_hits))
        return IntentResult(Intent.KPI_ANALYTICS, conf, analytics_hits, entities, terms)
    if is_rcm:
        conf = min(0.95, 0.6 + 0.1 * (len(terms) + len(vocab_hits)))
        return IntentResult(Intent.RCM_KNOWLEDGE, conf, terms + vocab_hits, entities, terms)
    if any(h in ql for h in _OFF_TOPIC_HINTS):
        return IntentResult(Intent.OUT_OF_SCOPE, 0.85, ["off_topic_hint"], entities, terms)
    # Unknown but not clearly off-topic: treat as a knowledge question with low confidence so
    # retrieval relevance (Phase 2) can make the final in/out-of-scope call.
    return IntentResult(Intent.RCM_KNOWLEDGE, 0.3, [], entities, terms)
