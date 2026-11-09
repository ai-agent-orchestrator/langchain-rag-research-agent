"""Token budget interfaces. M0: protocols and fakes only; no reduction logic."""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass
from typing import Protocol, Sequence

from rag_research_agent.core.types import Segment


@dataclass(frozen=True)
class BudgetCheck:
    within: bool
    tokens: int
    limit: int


class TokenBudget(Protocol):
    def check(self, segments: Sequence[Segment]) -> BudgetCheck: ...


class Dieter(Protocol):
    def reduce(self, segments: Sequence[Segment], round_index: int) -> list[Segment]: ...


class FakeTokenBudget:
    def __init__(self, limit: int = 1000):
        self.limit = limit

    def check(self, segments: Sequence[Segment]) -> BudgetCheck:
        tokens = sum(s.end - s.start for s in segments)
        return BudgetCheck(tokens <= self.limit, tokens, self.limit)


class FakeDieter:
    """Never removes anything (so it can never silently truncate)."""
    def reduce(self, segments: Sequence[Segment], round_index: int) -> list[Segment]:
        return list(segments)
