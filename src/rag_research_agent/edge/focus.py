"""Focus keywords: chosen by the person (key players, a time like "2025년") and/or by meaningful
word frequency in the draft. Stdlib only, no morphology model: a light particle strip, then counting."""
from __future__ import annotations

MATURITY = "incubating"

import re
from collections import Counter

MAX_FOCUS = 5
_TOKEN = re.compile(r"[가-힣A-Za-z0-9][가-힣A-Za-z0-9.%]*")
# longest first, so "에서" is stripped before "에"
_PARTICLES = sorted(("은", "는", "이", "가", "을", "를", "의", "에", "에서", "에게", "으로", "로", "와", "과", "도",
                     "만", "까지", "부터", "보다", "처럼", "이며", "이고", "이다", "였다", "했다", "하는", "한"),
                    key=len, reverse=True)
STOPWORDS = frozenset((
    "그리고", "그러나", "하지만", "또한", "이번", "이후", "이전", "대한", "통해", "위해", "따라", "있다", "없다",
    "것이", "것은", "것을", "수준", "경우", "때문", "모두", "가장", "대비", "기준", "결과", "관련", "정도",
    "중요한", "의미를", "주목", "필요", "다양한", "상황", "앞으로", "향후", "the", "and", "of", "to", "in",
))


def normalize(token: str) -> str:
    for p in _PARTICLES:
        if token.endswith(p) and len(token) - len(p) >= 2:
            return token[: -len(p)]
    return token


def frequent_terms(text: str, min_count: int = 2, limit: int = MAX_FOCUS, exclude=()) -> list[tuple[str, int]]:
    """Terms appearing at least min_count times, most frequent first; numbers-only tokens are skipped."""
    counts = Counter()
    for raw in _TOKEN.findall(text):
        base = raw.rstrip(".")
        term = next((e for e in exclude if base.startswith(e) and normalize(base) in (e, base)), None) or normalize(base)
        if (len(term) < 2 or term in STOPWORDS or term in exclude or re.fullmatch(r"[\d.,%]+", term)
                or raw.rstrip(".").endswith(("다", "고", "며", "면", "서", "지만"))):   # predicates / connectives
            continue
        counts[term] += 1
    ranked = sorted(((t, c) for t, c in counts.items() if c >= min_count), key=lambda x: (-x[1], x[0]))
    return ranked[:limit]


def build_focus(text: str, manual: dict[str, float] | None = None, auto_min_count: int | None = None,
                exclude=()) -> dict[str, float]:
    """Manual keywords first (key players, times, anything typed), then fill the remaining slots by frequency."""
    focus = dict(manual or {})
    if len(focus) > MAX_FOCUS:
        raise ValueError(f"at most {MAX_FOCUS} focus keywords (got {len(focus)})")
    if auto_min_count:
        for term, _ in frequent_terms(text, auto_min_count, MAX_FOCUS - len(focus), exclude=set(exclude) | set(focus)):
            focus[term] = 1.0
    return focus
