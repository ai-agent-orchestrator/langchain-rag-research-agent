"""Edge scoring interfaces. M0: protocols and fakes only; no scoring logic or weights."""
from __future__ import annotations

MATURITY = "incubating"

from typing import Protocol, Sequence

from rag_research_agent.core.types import Candidate, EdgeScore, Segment


class EdgeScorer(Protocol):
    def score(self, segments: Sequence[Segment]) -> list[EdgeScore]: ...


class ProtectedPicker(Protocol):
    def pick(self, segments: Sequence[Segment], scores: Sequence[EdgeScore]) -> list[Candidate]: ...


class FakeEdgeScorer:
    """All-zero scores. Test stand-in; weights are not decided in M0."""
    def score(self, segments: Sequence[Segment]) -> list[EdgeScore]:
        return [EdgeScore(segment_id=s.segment_id, scorer_version="fake") for s in segments]


class FakeProtectedPicker:
    def pick(self, segments: Sequence[Segment], scores: Sequence[EdgeScore]) -> list[Candidate]:
        return []
