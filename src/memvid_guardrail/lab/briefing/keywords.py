"""LAB: keyword enhancement for long prompts.

- tokenize(): Korean-friendly terms. Strips common particles/endings so "반환이" and "반환을"
  both count as "반환" (a light heuristic, not a morphological analyzer).
- BM25 over segments (pure Python).
- salient_terms(): terms that characterise the document (frequent overall, concentrated in
  few segments).
- expand_query(): pseudo-relevance feedback. Take the top BM25 segments for the task and add
  their most characteristic terms that the task did not mention.
"""
from __future__ import annotations

MATURITY = "lab"

import math
import re
from collections import Counter
from typing import Sequence

# Longest first, so "에서는" is removed before "는".
_SUFFIXES = sorted("""은 는 이 가 을 를 에 의 도 만 와 과 로 으로 에서 에게 한테 까지 부터 처럼 보다 이나 나
에서는 에는 으로는 로는 이라는 라는 이라고 라고 입니다 합니다 했다 한다 하는 하고 하며 해야 되는 된다 이며 이고
이다 였다 했습니다 됩니다 하지 않는다 않습니다""".split(), key=len, reverse=True)
_STOP = {"그리고", "그러나", "하지만", "또는", "있다", "없다", "있는", "없는", "경우", "때문", "위해", "대한", "관련",
         "이번", "해당", "모든", "각각", "등을", "the", "and", "for", "with", "that", "this", "are", "not"}
_TOKEN = re.compile(r"[가-힣]+|[A-Za-z][A-Za-z0-9_\-]*|\d[\d,.:/\-]*")


def _stem(token: str) -> str:
    if not re.fullmatch(r"[가-힣]+", token):
        return token.lower()
    for suffix in _SUFFIXES:
        if len(token) - len(suffix) >= 2 and token.endswith(suffix):
            return token[: -len(suffix)]
    return token


def tokenize(text: str) -> list[str]:
    out = []
    for raw in _TOKEN.findall(text):
        term = _stem(raw)
        if len(term) >= 2 and term not in _STOP:
            out.append(term)
    return out


class BM25:
    def __init__(self, segments: Sequence[str], k1: float = 1.5, b: float = 0.75):
        self.docs = [Counter(tokenize(s)) for s in segments]
        self.lengths = [sum(d.values()) for d in self.docs]
        self.avg = (sum(self.lengths) / len(self.lengths)) if self.lengths else 0.0
        self.k1, self.b = k1, b
        df = Counter(t for d in self.docs for t in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query_terms: Sequence[str]) -> list[float]:
        out = []
        for doc, length in zip(self.docs, self.lengths):
            s = 0.0
            for term in query_terms:
                tf = doc.get(term, 0)
                if tf:
                    norm = tf * (self.k1 + 1) / (tf + self.k1 * (1 - self.b + self.b * length / (self.avg or 1)))
                    s += self.idf.get(term, 0.0) * norm
            out.append(s)
        return out


def salient_terms(segments: Sequence[str], k: int = 30) -> list[str]:
    """tf-idf summed over segments: frequent in the document but not spread everywhere."""
    docs = [Counter(tokenize(s)) for s in segments]
    n = len(docs) or 1
    df = Counter(t for d in docs for t in d)
    score: Counter = Counter()
    for d in docs:
        total = sum(d.values()) or 1
        for term, tf in d.items():
            score[term] += (tf / total) * math.log(1 + n / df[term])
    return [t for t, _ in score.most_common(k)]


def expand_query(task: str, segments: Sequence[str], bm25: BM25, feedback_segments: int = 3,
                 add_terms: int = 8) -> list[str]:
    base = list(dict.fromkeys(tokenize(task)))
    scores = bm25.scores(base)
    top = sorted(range(len(segments)), key=lambda i: -scores[i])[:feedback_segments]
    top = [i for i in top if scores[i] > 0]
    if not top:
        return base
    extra = [t for t in salient_terms([segments[i] for i in top], k=add_terms * 3) if t not in base]
    return base + extra[:add_terms]
