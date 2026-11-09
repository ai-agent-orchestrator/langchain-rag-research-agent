"""Retrieval interfaces."""
from __future__ import annotations

MATURITY = "incubating"

from typing import Protocol, Sequence

from rag_research_agent.core.types import Candidate, Knobs


class Retriever(Protocol):
    def retrieve(self, query: str, knobs: Knobs) -> list[Candidate]: ...


class Reranker(Protocol):
    def rerank(self, query: str, candidates: Sequence[Candidate]) -> list[Candidate]: ...


class FakeRetriever:
    def retrieve(self, query: str, knobs: Knobs) -> list[Candidate]:
        return []


class FakeReranker:
    def rerank(self, query: str, candidates: Sequence[Candidate]) -> list[Candidate]:
        return sorted(candidates, key=lambda c: -c.relevance)
