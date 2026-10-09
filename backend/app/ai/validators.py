"""Deterministic response validation for SLM output.

The fine-tuned 1.7B model is fluent but not reliable on facts (e.g. it expands "ERA" to
"Electronic Retrieval Agreement"). Every answer passes through these checks before it is
returned. Error-severity issues trigger regeneration with stronger grounding and, if that
still fails, a fallback to the validated knowledge-base definition.

Checks:
  - empty / truncated output
  - excessive repetition
  - PHI-like content
  - critical terminology (acronym expansions, forbidden misdefinitions, required concepts)
  - KPI formulas
  - numbers not supported by references / data / question
  - identifiers (claim / payer / provider IDs) not supported by references / data / question
  - missing or invalid citations when references were supplied
  - relevance to the question
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml

from app.core.config import REPO_ROOT

Severity = Literal["info", "warning", "error"]

VALIDATED_TERMS_PATH = REPO_ROOT / "knowledge" / "validated_terms.yaml"


@dataclass
class ValidationIssue:
    code: str
    severity: Severity
    message: str
    term: str | None = None


@dataclass
class ValidationReport:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not any(i.severity == "error" for i in self.issues)

    @property
    def term_errors(self) -> list[ValidationIssue]:
        return [i for i in self.issues if i.severity == "error" and i.term]

    def correction_hint(self) -> str:
        return "; ".join(i.message for i in self.issues if i.severity == "error")


# --------------------------------------------------------------------------- validated terms
@dataclass(frozen=True)
class TermRule:
    key: str
    name: str
    aliases: tuple[str, ...]
    acronyms: tuple[str, ...]
    expansion: str | None
    definition: str
    source: str
    required_any: tuple[str, ...]
    forbidden: tuple[str, ...]
    formula: str | None
    formula_required_all: tuple[str, ...]


@lru_cache
def load_term_rules(path: Path = VALIDATED_TERMS_PATH) -> dict[str, TermRule]:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rules = {}
    for key, t in raw.get("terms", {}).items():
        rules[key] = TermRule(
            key=key,
            name=t["name"],
            aliases=tuple(a.lower() for a in t.get("aliases", [])),
            acronyms=tuple(t.get("acronyms", [])),
            expansion=t.get("expansion"),
            definition=" ".join(t["definition"].split()),
            source=t.get("source", "RCM validated terms"),
            required_any=tuple(s.lower() for s in t.get("required_any", [])),
            forbidden=tuple(s.lower() for s in t.get("forbidden", [])),
            formula=t.get("formula"),
            formula_required_all=tuple(s.lower() for s in t.get("formula_required_all", [])),
        )
    return rules


# --------------------------------------------------------------------------- helpers
_WORD_RE = re.compile(r"[a-z][a-z0-9/'-]+")
_STOP = set(
    "a an the and or of to in on for with by is are was were be been being as at from that this these those "
    "it its into than then there their they them what which who whom how why when where can could should "
    "would will may might must do does did not no yes if but so such also about your you we our us any all "
    "each more most other some only own same very just over under between both before after up down out".split()
)

_PHI_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("phone", re.compile(r"(?<!\d)\(?\d{3}\)?[\s.-]\d{3}[\s.-]\d{4}(?!\d)")),
    ("email", re.compile(r"\b[\w.+-]+@[\w-]+\.[a-z]{2,}\b", re.I)),
    ("mrn", re.compile(r"\bMRN[:#\s]*[A-Z0-9]{5,}\b", re.I)),
    ("dob", re.compile(r"\b(?:DOB|date of birth)[:\s]*\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", re.I)),
    ("member_id", re.compile(r"\b(?:member|subscriber|policy)\s*(?:id|number|#)[:#\s]*[A-Z0-9]{6,}\b", re.I)),
]

_NUM_RE = re.compile(
    r"(?<![\w.])(?P<cur>\$)?(?P<num>\d[\d,]*(?:\.\d+)?)(?P<pct>%)?"
    r"(?:\s?(?P<suf>[kKmM]\b|thousand\b|million\b))?"
)
_CITE_RE = re.compile(r"\[(\d{1,2})\]")

# Identifiers the model must never invent. The fine-tuning data paired masked inputs
# (<CLAIM_ID>, <PROVIDER_ID>) with real IDs in the outputs, so the model learned to emit claim
# numbers it was never shown. Covers database IDs (CLM-001234, PYR-MCR, PRV-01), long numeric
# IDs (9+ digits, e.g. claim numbers) and anonymisation placeholders copied from training inputs.
_ID_RE = re.compile(
    r"\bCLM[-_ ]?\d{4,10}\b|\bCLAIM[-_]\d{4,10}\b|\b(?:PYR|PRV)-[A-Z0-9]{2,4}\b"
    r"|(?<![\w.,$])\d{9,}(?![\w]|[.,]\d)|<[A-Z][A-Z_]*_ID>",
    re.IGNORECASE,
)
ID_REDACTION = "[unverified ID removed]"


def _id_key(token: str) -> str:
    t = token.upper()
    m = re.fullmatch(r"(?:CLM|CLAIM)[-_ ]?(\d+)", t)
    return f"CLM-{m.group(1)}" if m else t


def _allowed_ids(sources: list[str]) -> set[str]:
    return {_id_key(m.group(0)) for s in sources if s for m in _ID_RE.finditer(s)}


def unsupported_identifiers(text: str, sources: list[str]) -> list[str]:
    """Identifiers in `text` that appear in none of `sources` (question, data, references)."""
    allowed = _allowed_ids(sources)
    out: list[str] = []
    for m in _ID_RE.finditer(text):
        if _id_key(m.group(0)) not in allowed and m.group(0) not in out:
            out.append(m.group(0))
    return out


def redact_identifiers(text: str, sources: list[str]) -> str:
    """Mask identifiers that are not supported by `sources`."""
    allowed = _allowed_ids(sources)
    return _ID_RE.sub(lambda m: m.group(0) if _id_key(m.group(0)) in allowed else ID_REDACTION, text)
_TRANSACTION_NUMBERS = {835.0, 837.0, 270.0, 271.0, 276.0, 277.0, 278.0, 999.0, 100.0}
_SUFFIX = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6}


def _num_value(m: re.Match[str]) -> float | None:
    try:
        v = float(m.group("num").replace(",", ""))
    except ValueError:
        return None
    suf = (m.group("suf") or "").lower()
    return v * _SUFFIX.get(suf, 1.0)


def _close(a: float, b: float) -> bool:
    """Equal up to rounding: absolute 0.051 (one decimal), 0.6 for whole numbers, or 1% for large values."""
    return abs(a - b) <= max(0.051, 0.006 * abs(b)) or (abs(b) >= 1 and abs(a - round(b)) < 0.51 and a.is_integer())


def content_words(text: str) -> set[str]:
    return {w for w in _WORD_RE.findall(text.lower()) if w not in _STOP and len(w) > 2}


def _stem(word: str) -> str:
    """Light suffix folding so "denials"/"denial" and "increased"/"increase" compare equal."""
    for suf in ("ing", "ed", "es", "s", "e"):
        if len(word) > len(suf) + 3 and word.endswith(suf) and not word.endswith("ss"):
            return word[: -len(suf)]
    return word


def term_forms(rule: TermRule) -> list[str]:
    forms = list(rule.aliases) + [a.lower() for a in rule.acronyms]
    if rule.expansion:
        forms.append(rule.expansion.lower())
    return forms


def contains_phrase(text_l: str, phrase: str) -> bool:
    return re.search(rf"(?<![\w/]){re.escape(phrase)}(?![\w/])", text_l) is not None


def _term_present(text_l: str, rule: TermRule) -> bool:
    return any(contains_phrase(text_l, f) for f in term_forms(rule))


def _acronym_expansions(text: str, acronym: str) -> list[str]:
    """Find expansions the text gives for an acronym: 'ERA (X Y Z)', 'X Y Z (ERA)', 'ERA stands for X Y Z'."""
    a = re.escape(acronym)
    found = []
    for m in re.finditer(rf"\b{a}s?\b\s*\(([A-Za-z][A-Za-z /&-]{{3,60}})\)", text):
        found.append(m.group(1))
    for m in re.finditer(rf"\b{a}s?\b\s*(?:\*\*)?\s*(?:stands for|is short for|means|refers to an?|is an?)\s+(?:\*\*)?(?:an?\s+|the\s+)?([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+){{1,4}})", text):
        found.append(m.group(1))
    words_before = r"((?:[A-Z][A-Za-z]+[\s-]+){1,5})"
    for m in re.finditer(rf"{words_before}\(\s*{a}\s*\)", text):
        found.append(m.group(1))
    return [f.strip(" *-") for f in found]


_COMPARE_Q_RE = re.compile(r"\b(difference|differ|vs\.?|versus|stand for|stands for|meaning of|mean by)\b", re.I)
_DEFINE_LEAD = r"^\s*(?:what\s+(?:is|are|does)|what's|define|explain|describe|tell me about)\s+(?:an?\s+|the\s+)?"


def is_definition_question(question: str, terms: list[str] | None = None) -> bool:
    """True when the user asks what a critical term *is* ("What is an ERA?", "ERA vs EOB"),
    not for questions that merely mention it ("What are the major causes of denials?")."""
    if _COMPARE_Q_RE.search(question):
        return True
    q = question.lower()
    rules = load_term_rules()
    for key in terms if terms is not None else rules:
        rule = rules.get(key)
        if rule and any(re.search(_DEFINE_LEAD + re.escape(f) + r"s?\b", q) for f in term_forms(rule)):
            return True
    return False


def _expansion_matches(found: str, expected: str) -> bool:
    f = content_words(found.replace("-", " "))
    e = content_words(expected.replace("-", " "))
    return bool(e) and len(f & e) / len(e) >= 0.67


# --------------------------------------------------------------------------- validator
class ResponseValidator:
    def __init__(self, term_rules: dict[str, TermRule] | None = None) -> None:
        self.term_rules = load_term_rules() if term_rules is None else term_rules

    def validate(
        self,
        answer: str,
        question: str,
        query_terms: list[str],
        reference_texts: list[str] | None = None,
        data_text: str | None = None,
        finish_reason: str = "stop",
    ) -> ValidationReport:
        rep = ValidationReport()
        text = answer.strip()
        reference_texts = reference_texts or []

        if len(text) < 20:
            rep.issues.append(ValidationIssue("empty_answer", "error", "The model returned an empty or near-empty answer."))
            return rep
        if finish_reason == "length":
            rep.issues.append(ValidationIssue("truncated", "warning", "Answer hit the token limit and may be incomplete."))

        self._check_repetition(text, rep)
        self._check_phi(text, rep)
        self._check_terms(text, question, query_terms, rep)
        self._check_numbers(text, question, reference_texts, data_text, rep)
        self._check_identifiers(text, question, reference_texts, data_text, rep)
        self._check_direction(text, data_text, rep)
        self._check_citations(text, len(reference_texts), rep)
        self._check_relevance(text, question, reference_texts + ([data_text] if data_text else []), rep)
        return rep

    # -- individual checks ---------------------------------------------------------------
    @staticmethod
    def _check_repetition(text: str, rep: ValidationReport) -> None:
        sentences = [s.strip().lower() for s in re.split(r"(?<=[.!?])\s+|\n+", text) if len(s.strip()) > 25]
        dupes = sum(c - 1 for c in Counter(sentences).values() if c > 1)
        words = _WORD_RE.findall(text.lower())
        grams = Counter(tuple(words[i : i + 6]) for i in range(max(0, len(words) - 5)))
        repeated_grams = sum(c - 1 for c in grams.values() if c > 2)
        if dupes >= 2 or repeated_grams >= 8:
            rep.issues.append(ValidationIssue("repetition", "error", "The answer repeats itself excessively."))
        elif dupes == 1 or repeated_grams >= 3:
            rep.issues.append(ValidationIssue("repetition", "warning", "The answer contains some repeated content."))

    @staticmethod
    def _check_phi(text: str, rep: ValidationReport) -> None:
        kinds = [k for k, p in _PHI_PATTERNS if p.search(text)]
        if kinds:
            rep.issues.append(ValidationIssue("phi_detected", "error", f"Answer contains PHI-like content ({', '.join(kinds)})."))

    def _check_terms(self, text: str, question: str, query_terms: list[str], rep: ValidationReport) -> None:
        text_l = text.lower()
        # Core-concept checks only make sense when the user asked what a term *is*.
        definitional = is_definition_question(question, query_terms)
        # Validate every critical term the question asks about, plus any the answer defines.
        keys = set(query_terms) | {k for k, r in self.term_rules.items() if _term_present(text_l, r)}
        for key in sorted(keys):
            rule = self.term_rules.get(key)
            if not rule:
                continue
            for acr in rule.acronyms:
                if not rule.expansion:
                    continue
                for exp in _acronym_expansions(text, acr):
                    if not _expansion_matches(exp, rule.expansion):
                        rep.issues.append(ValidationIssue(
                            "incorrect_expansion", "error",
                            f"'{acr}' was expanded as '{exp}', but it means '{rule.expansion}'.", key))
            for bad in rule.forbidden:
                if bad in text_l:
                    rep.issues.append(ValidationIssue(
                        "incorrect_definition", "error",
                        f"Answer describes {rule.name} as '{bad}', which is incorrect.", key))
            if (definitional and key in query_terms and rule.required_any
                    and not any(r in text_l for r in rule.required_any)):
                rep.issues.append(ValidationIssue(
                    "missing_core_concept", "error",
                    f"Answer about {rule.name} omits its core concept ({' / '.join(rule.required_any[:3])}).", key))
            if rule.formula and rule.formula_required_all:
                for sentence in self._formula_sentences(text_l, rule):
                    if any(r not in sentence for r in rule.formula_required_all):
                        rep.issues.append(ValidationIssue(
                            "incorrect_formula", "error",
                            f"{rule.name} formula is incorrect; the correct formula is: {rule.formula}.", key))
                        break

    _FORMULA_MARK = re.compile(r"(=|divided by|÷|\bformula\b|calculated (as|by)|\bx 100\b|\* 100|×)")

    @classmethod
    def _formula_sentences(cls, text_l: str, rule: TermRule) -> list[str]:
        """Sentences that state a formula for this term (term mentioned + formula marker)."""
        sentences = re.split(r"(?<=[.!?])\s+|\n+", text_l)
        out = []
        for i, s in enumerate(sentences):
            if cls._FORMULA_MARK.search(s) and _term_present(s, rule):
                # A formula often continues on the next line ("Formula:\nX / Y").
                out.append(s + " " + (sentences[i + 1] if i + 1 < len(sentences) else ""))
        return out

    @staticmethod
    def _check_numbers(text: str, question: str, refs: list[str], data_text: str | None, rep: ValidationReport) -> None:
        allowed_src = " ".join([question, data_text or "", *refs])
        allowed = [v for v in (_num_value(m) for m in _NUM_RE.finditer(allowed_src)) if v is not None]
        # Strip citation markers, list numbering and identifiers (checked separately) before scanning.
        body = _CITE_RE.sub("", text)
        body = re.sub(r"(?m)^\s*\d+[.)]\s", "", body)
        body = _ID_RE.sub(" ", body)
        unsupported = []
        for m in _NUM_RE.finditer(body):
            tok, val = m.group(0).strip(), _num_value(m)
            if val is None:
                continue
            is_money_or_pct = "$" in tok or "%" in tok
            # Small integers, years and transaction-set numbers are not factual claims worth flagging.
            if (not is_money_or_pct and (abs(val) <= 10 or (1990 <= val <= 2100 and val.is_integer()))) \
                    or val in _TRANSACTION_NUMBERS:
                continue
            if any(_close(val, a) for a in allowed):
                continue
            unsupported.append(tok)
        if unsupported:
            sev: Severity = "error" if data_text else "warning"
            rep.issues.append(ValidationIssue(
                "unsupported_numbers", sev,
                f"Numbers not found in the references or data: {', '.join(sorted(set(unsupported))[:6])}."))

    @staticmethod
    def _check_identifiers(text: str, question: str, refs: list[str], data_text: str | None,
                           rep: ValidationReport) -> None:
        bad = unsupported_identifiers(text, [question, data_text or "", *refs])
        if bad:
            rep.issues.append(ValidationIssue(
                "unsupported_identifier", "error",
                f"Identifiers not found in the question, data or references: {', '.join(bad[:6])}. "
                "Do not state any claim, payer or provider identifier that is not given."))

    _DIRECTION_RE = re.compile(r"Direction: [^\n]*?\b(increased|decreased|essentially unchanged)\b", re.I)
    _UP_RE = re.compile(r"\b(increas\w*|ros[e]|risen|grew|grown|went up|higher|spike\w*|jump\w*)\b", re.I)
    _DOWN_RE = re.compile(r"\b(decreas\w*|declin\w*|fell|fallen|dropp\w*|went down|lower\w*|improv\w*)\b", re.I)

    @classmethod
    def _check_direction(cls, text: str, data_text: str | None, rep: ValidationReport) -> None:
        """The headline sentence must not contradict the computed direction of change."""
        m = cls._DIRECTION_RE.search(data_text or "")
        if not m:
            return
        expected = m.group(1).lower()
        lead = re.split(r"(?<=[.!?])\s+", re.sub(r"\*\*[^*]+:\*\*", "", text).strip(), maxsplit=1)[0]
        up, down = bool(cls._UP_RE.search(lead)), bool(cls._DOWN_RE.search(lead))
        if (expected == "increased" and down and not up) or (expected == "decreased" and up and not down):
            rep.issues.append(ValidationIssue(
                "direction_mismatch", "error",
                f"The answer's headline contradicts the data: the metric {expected}."))

    @staticmethod
    def _check_citations(text: str, n_refs: int, rep: ValidationReport) -> None:
        if n_refs == 0:
            return
        cited = {int(c) for c in _CITE_RE.findall(text)}
        invalid = sorted(c for c in cited if c < 1 or c > n_refs)
        if invalid:
            rep.issues.append(ValidationIssue("invalid_citation", "warning", f"Cites non-existent references {invalid}."))
        if not cited:
            rep.issues.append(ValidationIssue("no_citation", "info", "Answer does not cite the supplied references."))

    @staticmethod
    def _check_relevance(text: str, question: str, refs: list[str], rep: ValidationReport) -> None:
        a = content_words(text)
        q = content_words(question) - {"rcm", "revenue", "cycle", "management", "explain", "difference", "define"}
        if q and not ({_stem(w) for w in a} & {_stem(w) for w in q}):
            rep.issues.append(ValidationIssue("irrelevant", "error", "The answer does not address the question."))
        if refs:
            r = content_words(" ".join(refs))
            overlap = len(a & r) / max(1, len(a))
            if overlap < 0.35:
                rep.issues.append(ValidationIssue(
                    "low_grounding", "warning",
                    f"Only {overlap:.0%} of the answer's vocabulary appears in the references; it may contain unsupported claims."))
