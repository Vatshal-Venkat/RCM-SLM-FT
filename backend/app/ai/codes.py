"""Remittance and billing code lookup: CARCs, group codes, RARCs and modifiers.

The 1.7B model does not reliably know what an individual code means (it described CO-16 as a
contractual write-off and modifier 25 as a separate procedure), and the knowledge base only
mentions codes in passing, so retrieval rarely surfaces the right one. Codes named in a question
are therefore looked up deterministically in knowledge/code_reference.yaml. Each entry becomes a
validated rule (validators.TermRule, kind="code") that is pinned into the prompt, checked in the
answer and returned verbatim if the model contradicts it twice.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

import yaml

from app.ai.validators import TermRule
from app.core.config import REPO_ROOT

CODE_REFERENCE_PATH = REPO_ROOT / "knowledge" / "code_reference.yaml"
SOURCE = "code_reference.yaml"

_GROUPS = "CO|PR|OA|PI"
# CO-16, PR 1, OA22, pi-253
_GROUP_CARC_RE = re.compile(rf"\b({_GROUPS})\s?-?\s?([A-Z]?\d{{1,3}})\b", re.I)
# "CARC 16", "denial code 197", "reason codes 16 and 29", "remark code N30"
_CONTEXT_RE = re.compile(
    r"\b(carcs?|rarcs?|remark codes?|(?:claim )?adjustment (?:reason )?codes?|denial (?:reason )?codes?|reason codes?)\b",
    re.I,
)
_CODE_TOKEN_RE = re.compile(r"\s*(?:#|no\.?|number)?\s*-?\s*([A-Z]{0,2}\d{1,3})\b", re.I)
_JOINER_RE = re.compile(r"\s*(?:,|and|or|&|/|vs\.?|versus)", re.I)
_BARE_RARC_RE = re.compile(r"\b(MA\d{2,3}|[MN]\d{1,3})\b", re.I)
# "modifier 25", "modifiers -59 and XS", "GA modifier"
_MODIFIER_AFTER_RE = re.compile(r"\bmodifiers?\b", re.I)
_MODIFIER_BEFORE_RE = re.compile(r"(?<![\w-])-?([0-9A-Z]{2})\s+modifiers?\b", re.I)
_MODIFIER_TOKEN_RE = re.compile(r"\s*(?:#)?\s*-?\s*([0-9A-Z]{2})\b", re.I)
_GROUP_CONTEXT_RE = re.compile(r"\bgroup codes?\b|\badjustment groups?\b", re.I)
_BARE_GROUP_RE = re.compile(rf"\b({_GROUPS})\b", re.I)


def _key(kind: str, code: str) -> str:
    return f"{kind}_{code.lower()}"


@lru_cache
def load_code_rules(path: Path = CODE_REFERENCE_PATH) -> dict[str, TermRule]:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    groups = {str(g): e for g, e in (raw.get("group_codes") or {}).items()}
    rules: dict[str, TermRule] = {}

    def add(key: str, name: str, aliases: list[str], definition: str, required: list[str]) -> None:
        rules[key] = TermRule(
            key=key, name=name, aliases=tuple(a.lower() for a in aliases), acronyms=(), expansion=None,
            definition=" ".join(definition.split()), source=SOURCE,
            required_any=tuple(r.lower() for r in required), forbidden=(), formula=None,
            formula_required_all=(), kind="code",
        )

    for g, e in groups.items():
        add(_key("group", g), f"Group code {g} ({e['name']})", [f"group code {g}"],
            f"Group code {g} means {e['name']}. {e['meaning']}", e.get("required_any", []))
    for c, e in (raw.get("carcs") or {}).items():
        c = str(c)
        group = e.get("group")
        group_txt = f" It is usually reported with group code {group} ({groups[group]['name']}), e.g. {group}-{c}." \
            if group in groups else ""
        add(_key("carc", c), f"CARC {c}", [f"carc {c}", *(f"{g.lower()}-{c}" for g in groups)],
            f"CARC {c} (Claim Adjustment Reason Code {c}) official description: \"{e['description']}\" "
            f"Meaning: {e['meaning']}{group_txt} Typical action: {e['action']}", e.get("required_any", []))
    for c, e in (raw.get("rarcs") or {}).items():
        c = str(c)
        add(_key("rarc", c), f"RARC {c}", [f"rarc {c}"],
            f"RARC {c} (Remittance Advice Remark Code {c}) official description: \"{e['description']}\" "
            f"Meaning: {e['meaning']}", e.get("required_any", []))
    for m, e in (raw.get("modifiers") or {}).items():
        m = str(m)
        add(_key("modifier", m), f"Modifier {m}", [f"modifier {m}", f"modifier -{m}"],
            f"Modifier {m} official description: \"{e['description']}\" Meaning: {e['meaning']}",
            e.get("required_any", []))
    return rules


def _tokens_after(text: str, pos: int, token_re: re.Pattern[str]) -> list[str]:
    """Code tokens directly following `pos`, allowing lists ("16, 29 and 50")."""
    out = []
    m = token_re.match(text, pos)
    while m:
        out.append(m.group(1).upper())
        j = _JOINER_RE.match(text, m.end())
        m = token_re.match(text, j.end()) if j else None
    return out


def detect_codes(text: str) -> list[str]:
    """Rule keys (carc_16, group_co, rarc_n30, modifier_25) for codes named in `text`, in order."""
    rules = load_code_rules()
    found: list[tuple[int, str]] = []

    def hit(pos: int, kind: str, code: str) -> None:
        key = _key(kind, code)
        if key in rules:
            found.append((pos, key))

    for m in _GROUP_CARC_RE.finditer(text):
        if _key("carc", m.group(2)) in rules:
            hit(m.start(), "carc", m.group(2))
            hit(m.start(), "group", m.group(1))
    for m in _CONTEXT_RE.finditer(text):
        remark = re.search(r"rarc|remark", m.group(1), re.I) is not None
        for code in _tokens_after(text, m.end(), _CODE_TOKEN_RE):
            primary, other = ("rarc", "carc") if remark else ("carc", "rarc")
            hit(m.start(), primary if _key(primary, code) in rules else other, code)
    if re.search(r"\brarcs?\b|\bremark codes?\b", text, re.I):
        for m in _BARE_RARC_RE.finditer(text):
            hit(m.start(), "rarc", m.group(1))
    for m in _MODIFIER_AFTER_RE.finditer(text):
        for code in _tokens_after(text, m.end(), _MODIFIER_TOKEN_RE):
            hit(m.start(), "modifier", code)
    for m in _MODIFIER_BEFORE_RE.finditer(text):
        hit(m.start(), "modifier", m.group(1))
    if _GROUP_CONTEXT_RE.search(text):
        for m in _BARE_GROUP_RE.finditer(text):
            hit(m.start(), "group", m.group(1))

    keys: list[str] = []
    for _, key in sorted(found, key=lambda x: x[0]):
        if key not in keys:
            keys.append(key)
    return keys
