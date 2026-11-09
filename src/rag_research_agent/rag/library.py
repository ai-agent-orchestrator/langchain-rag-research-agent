"""Research library v0: documents -> paragraph chunks -> embeddings -> Chroma, then search and an
Equalizer brief over the retrieved chunks (design flow: retrieve, then filter by a profile).

Every part is replaceable: the embedder (FakeEmbedder by default, E5 later), the store (Chroma by
default; memvid kept as an alternative), the profile. The manifest records the embedder identity and
refuses to reopen with a different one.
"""
from __future__ import annotations

MATURITY = "incubating"

import json
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from rag_research_agent.core.contracts import Chunk, RetrievalUnavailable
from rag_research_agent.embed.providers import FakeEmbedder
from rag_research_agent.ingest.paragraphs import paragraph_chunks
from rag_research_agent.store.chroma_store import ChromaIndex, publish_chroma

MANIFEST = "library_manifest.json"


def _embedder_id(e) -> str:
    return f"{getattr(e, 'model_id', type(e).__name__)}@{getattr(e, 'revision', '?')}:{getattr(e, 'dimension', '?')}"


class Library:
    def __init__(self, path: str | Path = ".runs/library", collection: str = "rra_library", embedder=None):
        self.path = Path(path)
        self.collection = collection
        self.embedder = embedder or FakeEmbedder(dimension=256)
        self.chunks: list[Chunk] = []
        self.index: ChromaIndex | None = None

    # ---- build / open
    def build(self, docs: Sequence[tuple[str, str, str]], max_chars: int = 600) -> "Library":
        """docs: (doc_id, title, text). Rebuilds the whole collection (v0: no incremental update)."""
        chunks = [c for doc_id, title, text in docs for c in paragraph_chunks(doc_id, title, text, max_chars=max_chars)]
        if not chunks:
            raise ValueError("no text to index")
        self.path.mkdir(parents=True, exist_ok=True)
        vectors = self.embedder.encode_documents([c.safe_text for c in chunks])
        self.index = publish_chroma(chunks, vectors, path=self.path / "chroma", collection=self.collection,
                                    dimension=self.embedder.dimension)
        self.chunks = chunks
        manifest = {"collection": self.collection, "embedder": _embedder_id(self.embedder),
                    "dimension": self.embedder.dimension, "chunks": [asdict(c) for c in chunks]}
        (self.path / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        return self

    def open(self) -> "Library":
        mf = self.path / MANIFEST
        if not mf.exists():
            raise RetrievalUnavailable(f"no library at {self.path}")
        data = json.loads(mf.read_text(encoding="utf-8"))
        if data["embedder"] != _embedder_id(self.embedder):
            raise RetrievalUnavailable(f"library was built with {data['embedder']}, not {_embedder_id(self.embedder)}")
        self.collection = data["collection"]
        self.chunks = [Chunk(**c) for c in data["chunks"]]
        self.index = ChromaIndex(self.path / "chroma", self.collection, self.chunks, data["dimension"])
        self.index.verify()
        return self

    # ---- search
    def search(self, query: str, k: int = 8, mode: str = "hybrid", rrf_k: int = 60) -> list[tuple[Chunk, float, int]]:
        if self.index is None:
            raise RetrievalUnavailable("library is not open")
        if mode == "vector":
            return self.index.search_vector(self.embedder.encode_query(query), k)
        if mode == "lex":
            return self.index.search_lex(query, k)
        if mode != "hybrid":
            raise ValueError("mode must be vector, lex or hybrid")
        width = max(k * 3, 10)
        fused: dict[str, float] = {}
        by_id: dict[str, Chunk] = {}
        for hits in (self.index.search_vector(self.embedder.encode_query(query), width), self.index.search_lex(query, width)):
            for chunk, _score, rank in hits:
                fused[chunk.chunk_id] = fused.get(chunk.chunk_id, 0.0) + 1.0 / (rrf_k + rank)
                by_id[chunk.chunk_id] = chunk
        ranked = sorted(fused.items(), key=lambda x: (-x[1], x[0]))[:k]
        return [(by_id[cid], round(score, 6), r + 1) for r, (cid, score) in enumerate(ranked)]

    # ---- equalizer on top of retrieval
    def brief(self, query: str, profile: str = "research", k: int = 8, budget: int = 800, mode: str = "hybrid",
              focus: dict[str, float] | None = None):
        """Retrieve k chunks, put them back in document order, and run the profile's Equalizer with the
        query as the task. Returns (brief, trace, hits)."""
        from rag_research_agent.rag.profile import Equalizer
        hits = self.search(query, k, mode)
        order = {c.chunk_id: i for i, c in enumerate(self.chunks)}
        draft = "\n\n".join(c.safe_text for c, _, _ in sorted(hits, key=lambda h: order[h[0].chunk_id]))
        brief, trace = Equalizer.from_profile(profile).brief(draft, task=query, budget=budget, focus=focus)
        return brief, trace, hits


def load_folder(folder: str | Path, patterns: Sequence[str] = ("*.txt", "*.md")) -> list[tuple[str, str, str]]:
    folder = Path(folder)
    docs = []
    for pattern in patterns:
        for f in sorted(folder.glob(pattern)):
            docs.append((f.stem, f.name, f.read_text(encoding="utf-8-sig")))
    return docs
