"""LAB: Reciprocal Rank Fusion of several rankings (e.g. memvid lex + vector).

RRF uses ranks only, so scores from different methods are never added directly.
Promotion to incubating requires: better Hit@3 than each single method on the same
evaluation set and no increase in no-evidence false passes.
"""
from __future__ import annotations

MATURITY = "lab"

from typing import Sequence


def rrf(rankings: Sequence[Sequence[str]], k: int = 60, weights: Sequence[float] | None = None) -> list[tuple[str, float]]:
    if k <= 0:
        raise ValueError("k must be positive")
    weights = list(weights) if weights is not None else [1.0] * len(rankings)
    if len(weights) != len(rankings):
        raise ValueError("one weight per ranking")
    fused: dict[str, float] = {}
    for ranking, weight in zip(rankings, weights):
        seen = set()
        for rank, doc in enumerate(ranking, start=1):
            if doc in seen:
                continue  # a ranking may list a document once
            seen.add(doc)
            fused[doc] = fused.get(doc, 0.0) + weight / (k + rank)
    return sorted(fused.items(), key=lambda kv: (-kv[1], kv[0]))
