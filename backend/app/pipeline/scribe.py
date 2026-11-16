"""AI scribe: turns a doctor-patient conversation into structured clinical facts and a SOAP note.

The conversation arrives as speaker-labelled utterances (live speech-to-text in the browser, or a
pasted transcript). Extraction is deterministic clinical NLP so every coded fact can be traced to
a quote:

* conditions are matched from the catalog and classified as affirmed, negated ("no cough"),
  uncertain ("could be strep": outpatient guidelines say do not code it) or someone else's
  history ("my neighbor had a brain tumor");
* a doctor's yes/no question takes its polarity from the patient's answer
  ("Any chest pain?" / "No." -> negated);
* services count as ordered only when the doctor states them (not when the patient asks, the
  doctor asks a non-offer question, or the test happened in the past);
* evidence tags (duration, failed conservative care, red flags...) feed medical necessity.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.pipeline import catalog as cat

# --------------------------------------------------------------------------- transcript parsing

_LABEL_RE = re.compile(
    r"^\s*(?:\[[^\]]*\]\s*)?(doctor|dr\.?|physician|provider|clinician|nurse|patient|pt\.?|d|p)\s*[:\-]\s*(.*)$", re.I)
_DOCTOR_LABELS = {"doctor", "dr", "dr.", "physician", "provider", "clinician", "nurse", "d"}


@dataclass
class Utterance:
    speaker: str  # doctor | patient | unknown
    text: str


def parse_transcript(raw: str) -> list[Utterance]:
    """'Doctor: ...' / 'Patient: ...' lines -> utterances. Unlabelled lines continue the last speaker."""
    out: list[Utterance] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        m = _LABEL_RE.match(line)
        if m:
            speaker = "doctor" if m.group(1).lower().rstrip(".") in {x.rstrip(".") for x in _DOCTOR_LABELS} else "patient"
            text = m.group(2).strip()
            if text:
                out.append(Utterance(speaker, text))
        elif out:
            out[-1].text = f"{out[-1].text} {line}"
        else:
            out.append(Utterance("unknown", line))
    return out


def normalize_utterances(items: list[dict]) -> list[Utterance]:
    out = []
    for it in items:
        text = " ".join(str(it.get("text", "")).split())
        if not text:
            continue
        speaker = str(it.get("speaker", "unknown")).lower()
        out.append(Utterance(speaker if speaker in ("doctor", "patient") else "unknown", text))
    return out


_SENT_RE = re.compile(r"(?<=[.?!])\s+")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT_RE.split(text) if s.strip()]


# --------------------------------------------------------------------------- context cues

_NEG_CUES = re.compile(
    r"\b(no|not|denies|denied|deny|without|negative for|never|none|free of|don'?t have|doesn'?t have|haven'?t had|"
    r"hasn'?t had|haven'?t|no signs? of|ruled out|don'?t need|no need for|won'?t need|hold off on|not going to)\b", re.I)
_UNCERTAIN_CUES = re.compile(
    r"\b(possible|possibly|probable|probably|likely|suspect\w*|could be|might be|may be|maybe|rule out|r/o|"
    r"concern(?:ed)? (?:about|for)|worried (?:about|it)|wonder(?:ing)? if|afraid (?:of|it))\b", re.I)
_OTHER_PERSON = re.compile(
    r"\b(mom|mother|dad|father|brother|sister|grandmother|grandfather|grandma|grandpa|aunt|uncle|neighbou?r|friend|"
    r"husband|wife|son|daughter|family|cousin|coworker)\b[^.?!]{0,30}\b(has|had|have|with|history|died)\b", re.I)
_PAST_CUES = re.compile(r"\b(last (?:year|time|visit|month|week)|already had|previous|prior|ago|back in \d{4})\b", re.I)
_OFFER_CUES = re.compile(r"\b(do you want|would you like|should we|shall we|can we|how about|want me to|okay if we|ok if we)\b", re.I)
_YES = re.compile(r"^\W*(yes|yeah|yep|yup|i do|it does|i have|sometimes|a little|kind of|definitely|uh-huh|mm-hmm|sure|okay|ok|please)\b", re.I)
_NO = re.compile(r"^\W*(no|nope|not really|never|i don'?t|it doesn'?t|i haven'?t|none|nah|not that i)\b", re.I)
_FOLLOWUP = re.compile(r"\b(follow up|follow-up|come back|see you in|return in|recheck in|call us)\b", re.I)
_EXAM = re.compile(
    r"\b(exam|look(?:s|ing)?|i see|tender\w*|swollen|swelling|red|clear|normal|range of motion|reflexes|strength|lungs|"
    r"heart sounds|temperature|blood pressure|heart rate|x-?rays? show|came back|patches|lymph nodes|regular)\b", re.I)
_PLAN = re.compile(
    r"\b(prescrib\w*|start(?:ing)? you on|increas\w*|decreas\w*|take|use|order\w*|refer\w*|i'?ll|we'?ll|let'?s|keep|"
    r"continue|give you|inject\w*|get|i want|i'?d like|i would like|we need|you need)\b", re.I)
_RX_VERBS = re.compile(r"\b(prescrib\w*|start(?:ing)? you on|increas\w* your|refill\w*|switch\w* you to)\b", re.I)
_CLAUSE_BREAK = re.compile(r"[,;:]|\bbut\b|\bthough\b|\bhowever\b", re.I)
_LOOK = re.compile(r"^\W*(?:let me|i'?ll|i will|let'?s) (?:take a |have a )?(?:look|listen)\b[^.?!]{0,30}[.!]?$", re.I)
# Acknowledgements ("Okay.", "Okay, let's do that.", "Thank you.") carry no history.
_FILLER = re.compile(
    r"^\W*(okay|ok|thanks|thank you|alright|all right|sure|great|bye|goodbye|yes|yeah|sounds good)\b"
    r"(?:\W+(?:let'?s do (?:that|it)|that'?s fine|thank you|thanks|doctor|doc))?\W*$"
    r"|^\W*(?:no|nope|not really|none)\W*$", re.I)  # bare "No." answers become pertinent negatives instead


def _window(sentence: str, start: int, words: int = 6) -> str:
    """Text just before a match, cut at the last clause break and limited to `words` words."""
    prefix = sentence[:start]
    parts = _CLAUSE_BREAK.split(prefix)
    tail = parts[-1] if parts else prefix
    # "No, no cough at all": the cue sits right before the break; keep a lone leading cue.
    if len(parts) > 1 and not tail.strip() and parts[-2].strip():
        tail = parts[-2]
    return " ".join(tail.split()[-words:])


def _first_sentence(u: Utterance | None) -> str:
    if u is None:
        return ""
    ss = sentences(u.text)
    return ss[0] if ss else ""


# --------------------------------------------------------------------------- extraction results


@dataclass
class Mention:
    key: str  # condition key or service code
    status: str  # affirmed | negated | uncertain | other_person | ordered | performed | reviewed | declined
    quote: str
    speaker: str
    side: str | None = None
    position: tuple[int, int, int] = (0, 0, 0)  # (utterance, sentence, char) of the first mention


@dataclass
class ScribeResult:
    utterances: list[Utterance]
    conditions: dict[str, Mention] = field(default_factory=dict)  # best mention per condition key
    not_coded: list[Mention] = field(default_factory=list)  # negated / uncertain / other person
    orders: dict[str, Mention] = field(default_factory=dict)  # service code -> mention
    rx: list[str] = field(default_factory=list)
    otc: list[str] = field(default_factory=list)
    evidence: dict[str, str] = field(default_factory=dict)  # tag -> quote
    vitals: dict[str, str] = field(default_factory=dict)
    exam: list[str] = field(default_factory=list)
    plan: list[str] = field(default_factory=list)
    hpi: list[str] = field(default_factory=list)
    follow_up: str | None = None


_STATUS_RANK = {"affirmed": 3, "uncertain": 2, "other_person": 1, "negated": 0}


def _compiled(phrases: tuple[str, ...]) -> list[re.Pattern[str]]:
    return [re.compile(rf"(?<![\w-]){p}(?![\w-])", re.I) for p in phrases]


_COND_RES = {c.key: _compiled(c.phrases) for c in cat.CONDITIONS}
_SERVICE_RES = {s.code: _compiled(s.phrases) for s in cat.SERVICES if s.phrases}
_DRUG_RES = [(d, re.compile(rf"\b{re.escape(d)}\b", re.I)) for d in cat.PRESCRIPTION_DRUGS]
_OTC_RES = [(d, re.compile(rf"\b{re.escape(d)}\b", re.I)) for d in cat.OTC_DRUGS]
_SIDE_RE = re.compile(r"\b(right|left)\b", re.I)


def _side_for(sentence: str, transcript_text: str, body: str) -> str | None:
    m = _SIDE_RE.search(sentence)
    if m:
        return m.group(1).lower()
    hits = re.findall(rf"\b(right|left)\s+{body}", transcript_text, re.I)
    if hits:
        rights = sum(h.lower() == "right" for h in hits)
        return "right" if rights >= len(hits) - rights else "left"
    return None


def extract(utterances: list[Utterance]) -> ScribeResult:
    res = ScribeResult(utterances=utterances)
    full_text = " ".join(u.text for u in utterances)

    for idx, u in enumerate(utterances):
        nxt = utterances[idx + 1] if idx + 1 < len(utterances) else None
        answer = _first_sentence(nxt) if nxt is not None and nxt.speaker != u.speaker else ""
        clinician = u.speaker in ("doctor", "unknown")
        for s_idx, s in enumerate(sentences(u.text)):
            question = s.endswith("?")
            followup = bool(_FOLLOWUP.search(s)) or s.lower().startswith("if ")

            # ---- conditions
            for key, pats in _COND_RES.items():
                for pat in pats:
                    m = pat.search(s)
                    if not m:
                        continue
                    win = _window(s, m.start())
                    if question:
                        if _YES.search(answer) and not _NO.search(answer):
                            status, quote = "affirmed", f'Q: "{s}" A: "{answer}"'
                        elif _NO.search(answer):
                            status, quote = "negated", f'Q: "{s}" A: "{answer}"'
                        else:
                            break  # unanswered question: no information
                    elif followup:
                        break  # "if the palpitations get worse, call us" is advice, not a finding
                    elif _OTHER_PERSON.search(s[: m.start()]):
                        status, quote = "other_person", s
                    elif _NEG_CUES.search(win):
                        status, quote = "negated", s
                    elif _UNCERTAIN_CUES.search(s[: m.start()]) and clinician:
                        status, quote = "uncertain", s
                    else:
                        status, quote = "affirmed", s
                    cond = cat.CONDITION_BY_KEY[key]
                    side = _side_for(s, full_text, "knee") if cond.lateral else None
                    mention = Mention(key, status, quote, u.speaker, side, (idx, s_idx, m.start()))
                    prev = res.conditions.get(key)
                    better = prev is None or _STATUS_RANK[status] > _STATUS_RANK[prev.status] or (
                        _STATUS_RANK[status] == _STATUS_RANK[prev.status] and u.speaker == "doctor" and prev.speaker != "doctor")
                    if better:
                        if prev is not None:
                            mention.position = min(prev.position, mention.position)
                        res.conditions[key] = mention
                    break

            # ---- services (orders come from the clinician)
            if clinician:
                for code, pats in _SERVICE_RES.items():
                    m = next((mm for p in pats if (mm := p.search(s))), None)
                    if not m:
                        continue
                    win = _window(s, m.start())
                    if question:
                        if _OFFER_CUES.search(s) and _YES.search(answer) and not _NO.search(answer):
                            status = "ordered"
                        else:
                            continue
                    elif _PAST_CUES.search(s):
                        status = "reviewed"
                    elif _NEG_CUES.search(win):
                        status = "declined"
                    elif re.search(r"\b(came back|results? (?:is|are|was|were)|shows?)\b", s, re.I):
                        status = "performed"
                    else:
                        status = "ordered"
                    side = _side_for(s, full_text, "knee") if cat.SERVICE_BY_CODE[code].lateral_modifier else None
                    prev = res.orders.get(code)
                    if prev is None or (prev.status in ("reviewed", "declined") and status in ("ordered", "performed")):
                        res.orders[code] = Mention(code, status, s if not question else f'Q: "{s}" A: "{answer}"', u.speaker, side)

                # ---- medications
                if not question:
                    for name, pat in _DRUG_RES:
                        m = pat.search(s)
                        if m and not _NEG_CUES.search(_window(s, m.start())) and name not in res.rx:
                            res.rx.append(name)
                    if _RX_VERBS.search(s) and not any(pat.search(s) for _, pat in _DRUG_RES):
                        res.rx.append("prescription (unnamed)")
                    for name, pat in _OTC_RES:
                        m = pat.search(s)
                        if m and not _NEG_CUES.search(_window(s, m.start())) and name not in res.otc:
                            res.otc.append(name)

            # ---- evidence tags for medical necessity
            if not question and not followup:
                for tag, pats in cat.EVIDENCE_RE.items():
                    if tag in res.evidence:
                        continue
                    for pat in pats:
                        m = pat.search(s)
                        if m and not _NEG_CUES.search(_window(s, m.start(), 3)):
                            res.evidence[tag] = s
                            break

            # ---- note sections
            if clinician and not question:
                _vitals(s, res.vitals)
                if _LOOK.search(s):
                    pass  # "Let me take a look." carries no clinical content
                elif followup and res.follow_up is None and _FOLLOWUP.search(s):
                    res.follow_up = s
                elif _EXAM.search(s) and not _PLAN.search(s):
                    res.exam.append(s)
                elif _PLAN.search(s):
                    res.plan.append(s)
            elif u.speaker == "patient" and not _FILLER.match(s) and not question:
                res.hpi.append(s)

    for key, m in list(res.conditions.items()):
        if m.status != "affirmed":
            res.not_coded.append(res.conditions.pop(key))
    return res


_BP = re.compile(r"\b(\d{2,3})\s*(?:over|/)\s*(\d{2,3})\b", re.I)
_TEMP = re.compile(r"\b(\d{2,3}(?:\.\d)?)\s*degrees", re.I)
_HR = re.compile(r"\bheart rate (?:is |of )?(\d{2,3})", re.I)
_SPO2 = re.compile(r"\b(?:oxygen|o2|sat\w*)(?: level)? (?:is |of )?(\d{2,3})\s*(?:%|percent)", re.I)


def _vitals(s: str, out: dict[str, str]) -> None:
    if (m := _BP.search(s)) and "blood pressure" in s.lower():
        out.setdefault("blood_pressure", f"{m.group(1)}/{m.group(2)} mmHg")
    if m := _TEMP.search(s):
        out.setdefault("temperature", f"{m.group(1)} °F")
    if m := _HR.search(s):
        out.setdefault("heart_rate", f"{m.group(1)} bpm")
    if m := _SPO2.search(s):
        out.setdefault("spo2", f"{m.group(1)}%")


# --------------------------------------------------------------------------- SOAP note

_NOT_CODED_REASON = {
    "negated": "Pertinent negative",
    "uncertain": "Uncertain diagnosis: outpatient guidelines code the symptoms, not a 'possible' condition",
    "other_person": "Refers to someone else, not the patient",
}


def build_note(res: ScribeResult, chief_complaint: str, diagnoses: list[dict], orders: list[dict]) -> dict:
    """SOAP note. `diagnoses` / `orders` come from the coder so the note and the claim agree."""
    negatives = [cat.CONDITION_BY_KEY[m.key].description for m in res.not_coded if m.status == "negated"]
    return {
        "chief_complaint": chief_complaint,
        "subjective": {
            "hpi": res.hpi[:8],
            "pertinent_negatives": negatives,
        },
        "objective": {"vitals": res.vitals, "exam": res.exam[:8]},
        "assessment": [{"code": d["code"], "description": d["description"]} for d in diagnoses],
        "plan": {
            "orders": [f'{o["code"]} {o["description"]}' for o in orders],
            "prescriptions": [r for r in res.rx],
            "otc": res.otc,
            "instructions": res.plan[:8],
            "follow_up": res.follow_up,
        },
        "not_coded": [
            {"finding": cat.CONDITION_BY_KEY[m.key].description, "reason": _NOT_CODED_REASON.get(m.status, m.status), "quote": m.quote}
            for m in res.not_coded
        ],
        "evidence": [{"tag": t, "label": cat.EVIDENCE_LABELS[t], "quote": q} for t, q in res.evidence.items()],
        "utterance_count": len(res.utterances),
        "generated_by": "AI scribe (clinical NLP); requires physician signature",
    }
