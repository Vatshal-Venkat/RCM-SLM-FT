"""Okapi BM25 lexical index.

Complements dense retrieval for exact RCM tokens that embeddings blur: acronyms (ERA, EOB,
CARC), transaction numbers (835, 277CA) and codes (CO-45, CARC 197).
"""

from __future__ import annotations

import math
import re
from collections import Counter

_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-/][a-z0-9]+)*")
_STOP = set(
    "a an the and or of to in on for with by is are was were be as at from that this it its into what which "
    "how why when where do does can could should would will may me my our we you your i explain define "
    "difference between tell about".split()
)


def tokenize(text: str) -> list[str]:
    toks = []
    for t in _TOKEN_RE.findall(text.lower()):
        if t in _STOP:
            continue
        toks.append(t)
        if "-" in t or "/" in t:  # index "first-pass" also as "first", "pass"
            toks.extend(p for p in re.split(r"[-/]", t) if p and p not in _STOP)
    # Light plural folding so "denials" matches "denial", "eras" matches "era".
    return [t[:-1] if len(t) > 3 and t.endswith("s") and not t.endswith("ss") else t for t in toks]


class BM25Index:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.doc_tokens = [tokenize(d) for d in docs]
        self.doc_len = [len(t) for t in self.doc_tokens]
        self.avgdl = sum(self.doc_len) / max(1, len(self.doc_len))
        self.tf = [Counter(t) for t in self.doc_tokens]
        df: Counter[str] = Counter()
        for toks in self.doc_tokens:
            df.update(set(toks))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: str) -> list[float]:
        q = tokenize(query)
        out = []
        for tf, dl in zip(self.tf, self.doc_len):
            s = 0.0
            for t in q:
                f = tf.get(t)
                if not f:
                    continue
                s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out.append(s)
        return out
