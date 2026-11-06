"""Relevance gate: top-k results alone never mean "evidence exists"."""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass
from typing import Sequence

from memvid_guardrail.core.contracts import (Chunk, Evidence, RetrievalMode, RetrievalResult,
                                            RetrievalStatus)


@dataclass(frozen=True)
class RelevanceRule:
    """Evidence exists when top1 >= tau_abs and (top1 - top2) >= tau_gap, on document scores.

    Document score = best chunk score of that document. Values are calibrated on the
    compare split and stored with `version`; there is no shared default like cosine 0.8.
    """
    mode: RetrievalMode
    tau_abs: float
    tau_gap: float
    version: str

    def passes(self, doc_scores: Sequence[float]) -> bool:
        if not doc_scores:
            return False
        top1 = doc_scores[0]
        top2 = doc_scores[1] if len(doc_scores) > 1 else 0.0
        return top1 >= self.tau_abs and (top1 - top2) >= self.tau_gap


def document_scores(hits: Sequence[tuple[Chunk, float, int]]) -> list[tuple[str, float]]:
    best: dict[str, float] = {}
    for chunk, score, _ in hits:
        best[chunk.document_id] = max(score, best.get(chunk.document_id, float("-inf")))
    return sorted(best.items(), key=lambda kv: kv[1], reverse=True)


def to_result(hits: Sequence[tuple[Chunk, float, int]], rule: RelevanceRule, index_version: str,
              k: int = 3) -> RetrievalResult:
    if not hits:
        return RetrievalResult(RetrievalStatus.EMPTY, rule.mode, index_version)
    if not rule.passes([s for _, s in document_scores(hits)]):
        return RetrievalResult(RetrievalStatus.BELOW_THRESHOLD, rule.mode, index_version)
    ordered = sorted(hits, key=lambda h: h[2])[:k]
    evidence = tuple(Evidence(c, rule.mode, s, r, index_version) for c, s, r in ordered)
    return RetrievalResult(RetrievalStatus.OK, rule.mode, index_version, evidence)
