"""Explicit reporting periods named in a question: "September 2026", "Q2", "May to July 2026",
"in 2025", "2026-05-01 to 2026-06-30".

Without this, "What was our denial rate in September 2026?" was answered from the default
90-day window and the model labelled that figure as September's. A named period always wins
over the relative windows ("last 30 days") handled in copilot_context.detect_window_days.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date

_MONTHS = {name.lower(): i for i, name in enumerate(calendar.month_name) if name}
_ABBR = {name.lower(): i for i, name in enumerate(calendar.month_abbr) if name} | {"sept": 9}
_FULL = "|".join(_MONTHS)
_ANY = "|".join(sorted(set(_MONTHS) | set(_ABBR), key=len, reverse=True))
_YEAR = r"(20\d{2})"
_PREP = r"(?:in|during|for|of|since|from|between|by|through|until|month of)"
_ORDINAL = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4}

_ISO_RANGE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})\s*(?:to|through|thru|until|and|-|–)\s*(\d{4}-\d{2}-\d{2})")
_MONTH_RANGE_RE = re.compile(
    rf"\b(?:between\s+)?({_ANY})\.?(?:\s+{_YEAR})?\s*(?:to|through|thru|until|and|-|–)\s*({_ANY})\.?(?:\s+{_YEAR})?\b")
# A month with a year ("Sep 2026"), after a preposition ("in September") or possessive
# ("September's"). Bare abbreviations and a bare "may" are too ambiguous to count.
_MONTH_YEAR_RE = re.compile(rf"\b({_ANY})\.?,?\s+{_YEAR}\b")
_MONTH_PREP_RE = re.compile(rf"\b{_PREP}\s+({_FULL})\b")
_MONTH_POSS_RE = re.compile(rf"\b({_FULL})'s\b")
_QUARTER_RE = re.compile(rf"\bq([1-4])(?:\s+{_YEAR})?\b|\b(first|second|third|fourth|1st|2nd|3rd|4th) quarter(?: of)?(?:\s+{_YEAR})?\b")
_YEAR_RE = re.compile(rf"\b(?:in|during|for|of|calendar year|year)\s+{_YEAR}\b")


@dataclass(frozen=True)
class Period:
    start: date
    end: date
    label: str
    # True when the period extends past the dataset's as-of date and was cut short.
    partial: bool = False


def _month_num(token: str) -> int:
    t = token.lower()
    return _MONTHS.get(t) or _ABBR[t]


def _month_end(y: int, m: int) -> date:
    return date(y, m, calendar.monthrange(y, m)[1])


def _latest_year(month: int, as_of: date) -> int:
    """Year of the most recent `month` that has started by `as_of`."""
    return as_of.year if month <= as_of.month else as_of.year - 1


def _clip(start: date, end: date, label: str, as_of: date) -> Period:
    return Period(start, min(end, as_of), label, partial=end > as_of >= start)


def parse_period(question: str, as_of: date) -> Period | None:
    q = question.lower()
    m = _ISO_RANGE_RE.search(q)
    if m:
        try:
            s, e = date.fromisoformat(m.group(1)), date.fromisoformat(m.group(2))
        except ValueError:
            return None
        return _clip(s, e, f"{s.isoformat()} to {e.isoformat()}", as_of) if s <= e else None

    m = _MONTH_RANGE_RE.search(q)
    if m and (m.group(2) or m.group(4) or re.search(rf"\b{_PREP}\s+{re.escape(m.group(1))}", q)):
        m1, m2 = _month_num(m.group(1)), _month_num(m.group(3))
        y2 = int(m.group(4)) if m.group(4) else (int(m.group(2)) if m.group(2) and m1 <= m2 else _latest_year(m2, as_of))
        y1 = int(m.group(2)) if m.group(2) else (y2 if m1 <= m2 else y2 - 1)
        s, e = date(y1, m1, 1), _month_end(y2, m2)
        if s <= e:
            return _clip(s, e, f"{calendar.month_name[m1]} {y1} to {calendar.month_name[m2]} {y2}", as_of)

    m = _QUARTER_RE.search(q)
    if m:
        qn = int(m.group(1)) if m.group(1) else _ORDINAL[m.group(3)]
        year_txt = m.group(2) or m.group(4)
        first = 3 * qn - 2
        y = int(year_txt) if year_txt else _latest_year(first, as_of)
        return _clip(date(y, first, 1), _month_end(y, first + 2), f"Q{qn} {y}", as_of)

    m = _MONTH_YEAR_RE.search(q)
    if m:
        mn, y = _month_num(m.group(1)), int(m.group(2))
    else:
        m = _MONTH_PREP_RE.search(q) or _MONTH_POSS_RE.search(q)
        if m:
            mn = _month_num(m.group(1))
            y = _latest_year(mn, as_of)
    if m:
        return _clip(date(y, mn, 1), _month_end(y, mn), f"{calendar.month_name[mn]} {y}", as_of)

    m = _YEAR_RE.search(q)
    if m:
        y = int(m.group(1))
        return _clip(date(y, 1, 1), date(y, 12, 31), str(y), as_of)
    return None


def mentions_period(question: str) -> bool:
    return parse_period(question, date.today()) is not None
