"""Wire a caller-owned Chroma index and embedder into the research SearchFn contract.

No model loading, publishing, implicit embedding provider, or index ownership here.
Without a masker, callers must supply already masked queries and Chunk.safe_text.
"""
from __future__ import annotations

MATURITY = "incubating"

import math

from rag_research_agent.core.contracts import RetrievalMode
from rag_research_agent.embed.providers import Embedder
from rag_research_agent.guard.protocols import Masker
from rag_research_agent.rag.research_graph import SearchFn
from rag_research_agent.retrieve.gate import RelevanceRule, to_result
from rag_research_agent.store.chroma_store import ChromaIndex


def make_chroma_search(index: ChromaIndex, embedder: Embedder, *,
                       rule: RelevanceRule | None = None,
                       masker: Masker | None = None) -> SearchFn:
    """Return (query, k) -> [(chunk_id, masked_text)] in Chroma rank order.

    The caller must match the embedder's model/revision/normalization to the index;
    ChromaIndex exposes only the dimension, which is checked here. A supplied rule
    uses the existing document-level absolute/gap gate, not a per-chunk cutoff.
    To include the second distinct document even behind many same-document chunks,
    gated searches inspect all indexed chunks before truncating to k. This costs
    more than ordinary top-k retrieval. Rule thresholds need separate calibration.
    The caller retains ownership and must close the index when finished.
    """
    if index.dimension != embedder.dimension:
        raise ValueError("index and embedder dimensions differ")
    if rule is not None and (
        rule.mode != RetrievalMode.VECTOR
        or not all(math.isfinite(v) for v in (rule.tau_abs, rule.tau_gap))
    ):
        raise ValueError("research Chroma search requires a finite vector relevance rule")

    def search(query: str, k: int) -> list[tuple[str, str]]:
        if isinstance(k, bool) or not isinstance(k, int):
            raise ValueError("k must be an integer")
        if k <= 0:
            return []
        count = index.vector_count()
        if count == 0:
            return []
        safe_query = masker.mask(query) if masker is not None else query
        vector = embedder.encode_query(safe_query)
        hits = index.search_vector(vector, k=count if rule is not None else min(k, count))
        if rule is not None:
            result = to_result(hits, rule, index.collection, k)
            chunks = [e.chunk for e in result.evidence]
        else:
            chunks = [chunk for chunk, _, _ in hits[:k]]
        return [(chunk.chunk_id, masker.mask(chunk.safe_text) if masker is not None else chunk.safe_text)
                for chunk in chunks]

    return search
