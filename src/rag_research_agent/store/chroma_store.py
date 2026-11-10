"""Chroma vector store adapter (optional extra `chroma`). Same search surface as MemvidIndex
(search_vector / search_lex / vector_count / close, hits as (Chunk, score, rank)), so either store can
be plugged in. Local persistent files only; Chroma's anonymized telemetry is switched off.

Owner decision 2026-11-09: develop with Chroma first (used in class), keep memvid swappable.
"""
from __future__ import annotations

MATURITY = "incubating"

import re
from pathlib import Path
from typing import Sequence

from rag_research_agent.core.contracts import Chunk, RetrievalUnavailable
from rag_research_agent.core.lexical import lex_terms
from rag_research_agent.store.retry import retry_io


def load_chroma():
    try:
        import chromadb
        from chromadb.config import Settings
    except ImportError as exc:  # pragma: no cover - exercised only without the extra
        raise RetrievalUnavailable("chromadb is not installed: pip install -e .[chroma]") from exc
    return chromadb, Settings


def _client(path: Path):
    chromadb, Settings = load_chroma()
    settings = Settings(anonymized_telemetry=False, allow_reset=False)
    return chromadb.PersistentClient(path=str(path), settings=settings)


def publish_chroma(chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]], *, path: Path,
                   collection: str, dimension: int, batch: int = 64) -> "ChromaIndex":
    """Write chunks + vectors into a fresh collection and verify every chunk is readable back."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,510}[A-Za-z0-9]", collection):
        raise ValueError("chroma collection names need 3-512 chars of [A-Za-z0-9._-], starting/ending alphanumeric")
    if len(chunks) != len(vectors):
        raise ValueError("chunks and vectors differ in length")
    if any(len(v) != dimension for v in vectors):
        raise ValueError("vector dimension mismatch")
    ids = [c.chunk_id for c in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate chunk_id")
    client = _client(path)
    try:
        retry_io(lambda: client.delete_collection(collection))
    except Exception:
        pass
    col = retry_io(lambda: client.create_collection(collection, metadata={"hnsw:space": "cosine", "dimension": dimension}))
    for i in range(0, len(chunks), batch):
        part = chunks[i:i + batch]
        retry_io(lambda: col.add(ids=[c.chunk_id for c in part], embeddings=[list(map(float, v)) for v in vectors[i:i + batch]],
                documents=[c.safe_text for c in part],
                metadatas=[{"document_id": c.document_id, "content_hash": c.content_hash} for c in part]))
    index = ChromaIndex(path, collection, chunks, dimension)
    index.verify()
    return index


class ChromaIndex:
    def __init__(self, path: Path, collection: str, chunks: Sequence[Chunk], dimension: int):
        self.path, self.collection, self.dimension = Path(path), collection, dimension
        self._by_id = {c.chunk_id: c for c in chunks}
        try:
            self._client = _client(self.path)
            self._col = self._client.get_collection(collection)
        except RetrievalUnavailable:
            raise
        except Exception as exc:
            raise RetrievalUnavailable(f"cannot open chroma collection: {type(exc).__name__}") from exc

    def verify(self) -> None:
        got = self._col.get(ids=list(self._by_id), include=["metadatas"])
        if sorted(got["ids"]) != sorted(self._by_id):
            raise RetrievalUnavailable("chroma collection does not contain exactly the expected chunks")
        for cid, meta in zip(got["ids"], got["metadatas"]):
            if meta.get("content_hash") != self._by_id[cid].content_hash:
                raise RetrievalUnavailable(f"content hash mismatch for {cid}")

    def _chunk(self, cid: str) -> Chunk:
        chunk = self._by_id.get(cid)
        if chunk is None:
            raise RetrievalUnavailable("index returned a chunk missing from the manifest")
        return chunk

    def search_vector(self, query_vector: Sequence[float], k: int = 10) -> list[tuple[Chunk, float, int]]:
        if len(query_vector) != self.dimension:
            raise RetrievalUnavailable("query vector dimension mismatch")
        try:
            res = self._col.query(query_embeddings=[list(map(float, query_vector))], n_results=min(k, len(self._by_id)),
                                  include=["distances"])
        except Exception as exc:
            raise RetrievalUnavailable(f"vector search failed: {type(exc).__name__}") from exc
        return [(self._chunk(cid), round(1.0 - float(d), 6), r + 1)
                for r, (cid, d) in enumerate(zip(res["ids"][0], res["distances"][0]))]

    def vector_count(self, any_vector: Sequence[float] | None = None) -> int:
        return int(self._col.count())

    def search_lex(self, query: str, k: int = 10) -> list[tuple[Chunk, float, int]]:
        """Keyword baseline: OR of whitespace terms (same term rule as the memvid adapter), scored by the
        number of distinct terms present. No Korean morphology."""
        terms = lex_terms(query)
        if not terms:
            return []
        scored = []
        for cid, chunk in self._by_id.items():
            hits = sum(1 for t in terms if t in chunk.safe_text)
            if hits:
                scored.append((hits, cid))
        scored.sort(key=lambda x: (-x[0], x[1]))
        return [(self._chunk(cid), float(h), r + 1) for r, (h, cid) in enumerate(scored[:k])]

    def close(self) -> None:
        """Release this client's ownership using Chroma's public, reference-counted API."""
        client = self._client
        try:
            if client is not None:
                client.close()
        finally:
            self._col = None
            self._client = None
