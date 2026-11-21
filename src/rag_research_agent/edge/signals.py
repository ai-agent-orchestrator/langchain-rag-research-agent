"""Three-signal structure: golden-rule edge, similarity, surprisal.

Structure only. This module defines the slots and a plain weighted sum so any scorer can be
plugged in. It ships no tuned weights, gates or thresholds: callers must pass their own.
Development of calibrated combinations continues outside this repository.
"""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass
from typing import Mapping, Protocol, Sequence

from rag_research_agent.core.types import Segment

SIGNALS = ("edge", "similarity", "surprisal")


class SurprisalScorer(Protocol):
    """Returns one information value per segment (e.g. mean -log p); higher = more surprising."""
    def score(self, texts: Sequence[str]) -> list[float]: ...


class FakeSurprisalScorer:
    """Test stand-in: every segment gets 0.0."""
    def score(self, texts: Sequence[str]) -> list[float]:
        return [0.0] * len(texts)


@dataclass(frozen=True)
class SegmentSignals:
    segment_id: str
    edge: float = 0.0
    similarity: float = 0.0
    surprisal: float = 0.0


def rank01(values: Sequence[float]) -> list[float]:
    """Within-document percentile (ties share the average rank); a single value maps to 0.5."""
    n = len(values)
    if n <= 1:
        return [0.5] * n
    order = sorted(range(n), key=lambda i: values[i])
    out, start = [0.0] * n, 0
    while start < n:
        end = start + 1
        while end < n and values[order[end]] == values[order[start]]:
            end += 1
        rank = (start + end - 1) / (2 * (n - 1))
        for i in order[start:end]:
            out[i] = rank
        start = end
    return out


def collect(segments: Sequence[Segment], edge: Sequence[float], similarity: Sequence[float],
            surprisal: Sequence[float], *, as_rank: bool = True) -> list[SegmentSignals]:
    """Align three per-segment signal lists. With as_rank, each list becomes a 0-1 percentile."""
    if not (len(segments) == len(edge) == len(similarity) == len(surprisal)):
        raise ValueError("every signal needs one value per segment")
    lists = [list(edge), list(similarity), list(surprisal)]
    if as_rank:
        lists = [rank01(v) for v in lists]
    return [SegmentSignals(s.segment_id, lists[0][i], lists[1][i], lists[2][i]) for i, s in enumerate(segments)]


def combine(signals: SegmentSignals, weights: Mapping[str, float]) -> float:
    """Plain weighted sum over the three signals. Weights are required and must be non-negative."""
    missing = [k for k in SIGNALS if k not in weights]
    if missing:
        raise ValueError(f"weights missing: {', '.join(missing)}")
    if any(weights[k] < 0 for k in SIGNALS):
        raise ValueError("weights must be non-negative")
    total = sum(weights[k] for k in SIGNALS)
    if total == 0:
        raise ValueError("at least one weight must be positive")
    return round(sum(weights[k] * getattr(signals, k) for k in SIGNALS) / total, 6)
