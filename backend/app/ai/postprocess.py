"""Deterministic clean-up of SLM output before validation and display."""

from __future__ import annotations

import re

SECTION_LABELS = [
    "Answer", "Why it matters", "Example", "Recommended actions", "Recommended action", "Key drivers",
    "Claim summary", "Current status", "Potential issue", "Explanation", "Recommended next action",
]
_LABEL_RE = re.compile(
    r"(?:^|(?<=\s))\**\s*(" + "|".join(re.escape(label) for label in SECTION_LABELS) + r")\s*:\s*\**\s*",
    re.IGNORECASE,
)


def strip_question_echo(text: str, question: str) -> str:
    """Small models sometimes restate the question before answering; drop that prefix."""
    t, q = text.lstrip(), question.strip().rstrip("?.! ")
    if q and t.lower().startswith(q.lower()):
        t = t[len(q):].lstrip("?.!:- \n")
    return t


_REF_ECHO_RE = re.compile(r"\n\s*\[\d{1,2}\][ \t]+\S[\s\S]*$")


def strip_reference_echo(text: str) -> str:
    """Drop a trailing copy of the reference list ("[1] Title ..."). Sources are attached
    separately; inline citations like "... posting [1]." are kept."""
    return _REF_ECHO_RE.sub("", text).rstrip()


def normalize_sections(text: str) -> str:
    """Render section labels consistently as '**Label:**' at the start of a line."""
    canonical = {label.lower(): label for label in SECTION_LABELS}

    def repl(m: re.Match[str]) -> str:
        return f"\n\n**{canonical[m.group(1).lower()]}:** "

    out = _LABEL_RE.sub(repl, text)
    out = re.sub(r"\n{3,}", "\n\n", out)
    # Section bodies that start a bullet list belong on the next line.
    out = re.sub(r"(\*\*[^*\n]+:\*\*)\s*\n?\s*(- )", r"\1\n\2", out)
    return out.strip()


def clean_answer(text: str, question: str) -> str:
    return normalize_sections(strip_reference_echo(strip_question_echo(text, question)))
