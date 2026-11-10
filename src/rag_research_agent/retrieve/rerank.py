"""Model-free chunk reranking baselines, independent of retrieval wiring."""
from __future__ import annotations

MATURITY = "incubating"

from typing import Protocol, Sequence

from rag_research_agent.core.contracts import Chunk
from rag_research_agent.core.lexical import lex_terms


class Reranker(Protocol):
    """Return chunks with scores in [0, 1], highest first; 확률 보정 아님.

    Scores describe this reranker's baseline, not a probability of relevance.
    Preserve input order for ties and retain the original chunk objects.
    """

    def rerank(self, query: str, chunks: Sequence[Chunk]) -> list[tuple[Chunk, float]]: ...


class IdentityReranker:
    """Keep input order; scores are normalized ordinal ranks (확률 보정 아님).

    For n > 1, rank i (zero-based) receives 1 - i / (n - 1).
    A singleton receives 1.0. The query does not affect this baseline.
    """

    def rerank(self, query: str, chunks: Sequence[Chunk]) -> list[tuple[Chunk, float]]:
        denominator = max(len(chunks) - 1, 1)
        return [(chunk, 1.0 - i / denominator) for i, chunk in enumerate(chunks)]


class LexicalOverlapReranker:
    """Rank by unique query-term coverage of safe_text (확률 보정 아님).

    Both sides use lex_terms, including its case-sensitive whitespace rules.
    Score = shared unique terms / unique query terms, or 0.0 for no terms.
    Repeated terms add no weight; ties retain input order. Titles are not scored.
    """

    def rerank(self, query: str, chunks: Sequence[Chunk]) -> list[tuple[Chunk, float]]:
        terms = set(lex_terms(query))
        scored = [
            (chunk, len(terms.intersection(lex_terms(chunk.safe_text))) / len(terms)
             if terms else 0.0)
            for chunk in chunks
        ]
        return sorted(scored, key=lambda item: item[1], reverse=True)
