"""Research library v0: documents -> paragraph chunks -> embeddings -> Chroma, then search and an
Equalizer brief over the retrieved chunks (design flow: retrieve, then filter by a profile).

Every part is replaceable: the embedder (FakeEmbedder by default, E5 later), the store (Chroma by
default; memvid kept as an alternative), the profile. The manifest records the embedder identity and
refuses to reopen with a different one.
"""
from __future__ import annotations

MATURITY = "incubating"

import json
from hashlib import sha256
from datetime import datetime, timezone
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from rag_research_agent.core.contracts import Chunk, RetrievalUnavailable
from rag_research_agent.embed.providers import FakeEmbedder
from rag_research_agent.ingest.paragraphs import paragraph_chunks
from rag_research_agent.store.chroma_store import ChromaIndex, publish_chroma, load_chroma

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
        self._documents = {}
        self.max_chars = 600

    # ---- build / open
    def build(self, docs: Sequence[tuple[str, str, str]], max_chars: int = 600) -> "Library":
        """docs: (doc_id, title, text). Explicitly rebuild the whole collection."""
        if len({d[0] for d in docs}) != len(docs):
            raise ValueError("duplicate document ID")
        self.max_chars = max_chars
        chunks = [c for doc_id, title, text in docs for c in paragraph_chunks(doc_id, title, text, max_chars=max_chars)]
        if not chunks:
            raise ValueError("no text to index")
        self.path.mkdir(parents=True, exist_ok=True)
        vectors = self.embedder.encode_documents([c.safe_text for c in chunks])
        self.index = publish_chroma(chunks, vectors, path=self.path / "chroma", collection=self.collection,
                                    dimension=self.embedder.dimension)
        self.chunks = chunks
        now = datetime.now(timezone.utc).isoformat()
        self._documents = {doc_id: {"doc_id": doc_id, "title": title, "hash": sha256(text.encode()).hexdigest(),
                                   "added_at": now} for doc_id, title, text in docs}
        self._save_manifest()
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
        self.max_chars = data.get("max_chars", 600)
        self._documents = data.get("documents", {})
        if not self._documents:
            for c in self.chunks:
                self._documents.setdefault(c.document_id, {"doc_id": c.document_id, "title": c.title,
                                                          "hash": None, "added_at": None})
        self.index = ChromaIndex(self.path / "chroma", self.collection, self.chunks, data["dimension"])
        self.verify()
        return self

    def _save_manifest(self):
        manifest = {"collection": self.collection, "embedder": _embedder_id(self.embedder),
                    "dimension": self.embedder.dimension, "chunks": [asdict(c) for c in self.chunks],
                    "documents": self._documents, "max_chars": self.max_chars}
        tmp = self.path / (MANIFEST + ".tmp")
        tmp.write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path / MANIFEST)

    def _collection(self):
        if self.index is None:
            raise RetrievalUnavailable("library is not open")
        # Public SDK API and public index path/name only; no _col / _by_id access.
        sdk, Settings = load_chroma()
        client = sdk.PersistentClient(path=str(self.index.path),
                                      settings=Settings(anonymized_telemetry=False, allow_reset=False))
        return client.get_collection(self.index.collection)

    def verify(self):
        col = self._collection()
        stored = col.get(include=["metadatas"])
        expected = {c.chunk_id: c for c in self.chunks}
        if set(stored["ids"]) != set(expected):
            raise RetrievalUnavailable("library manifest and collection IDs differ")
        for cid, metadata in zip(stored["ids"], stored["metadatas"]):
            if metadata.get("content_hash") != expected[cid].content_hash:
                raise RetrievalUnavailable(f"library content hash mismatch: {cid}")

    def _refresh(self):
        self.index = ChromaIndex(self.path / "chroma", self.collection, self.chunks, self.embedder.dimension)
        self.verify()
        self._save_manifest()

    def documents(self):
        return [{**info, "chunks": sum(c.document_id == doc_id for c in self.chunks)}
                for doc_id, info in sorted(self._documents.items())]

    def add(self, docs):
        docs = list(docs)
        if len({d[0] for d in docs}) != len(docs):
            raise ValueError("duplicate document ID")
        if self.index is None:
            if (self.path / MANIFEST).exists():
                self.open()
            else:
                self.build(docs)
                return {"added": len(docs), "replaced": 0, "skipped": 0}
        self.verify()
        prepared, counts = [], {"added": 0, "replaced": 0, "skipped": 0}
        for doc_id, title, text in docs:
            digest = sha256(text.encode()).hexdigest()
            old = self._documents.get(doc_id)
            if old and old["hash"] == digest:
                counts["skipped"] += 1
                continue
            chunks = paragraph_chunks(doc_id, title, text, max_chars=self.max_chars)
            if not chunks:
                raise ValueError(f"no text to index: {doc_id}")
            vectors = self.embedder.encode_documents([c.safe_text for c in chunks])
            prepared.append((doc_id, title, digest, old, chunks, vectors))
        col = self._collection()
        for doc_id, title, digest, old, chunks, vectors in prepared:
            ids = [c.chunk_id for c in self.chunks if c.document_id == doc_id]
            if ids:
                col.delete(ids=ids)
            col.add(ids=[c.chunk_id for c in chunks], embeddings=vectors,
                    documents=[c.safe_text for c in chunks],
                    metadatas=[{"document_id": c.document_id, "content_hash": c.content_hash} for c in chunks])
            self.chunks = [c for c in self.chunks if c.document_id != doc_id] + list(chunks)
            self._documents[doc_id] = {"doc_id": doc_id, "title": title, "hash": digest,
                                       "added_at": old["added_at"] if old else datetime.now(timezone.utc).isoformat()}
            counts["replaced" if old else "added"] += 1
        self._refresh()
        return counts

    def remove(self, doc_id):
        self.verify()
        if doc_id not in self._documents:
            return False
        ids = [c.chunk_id for c in self.chunks if c.document_id == doc_id]
        if ids:
            self._collection().delete(ids=ids)
        self.chunks = [c for c in self.chunks if c.document_id != doc_id]
        del self._documents[doc_id]
        self._refresh()
        return True

    # ---- search
    def search(self, query: str, k: int = 8, mode: str = "hybrid", rrf_k: int = 60) -> list[tuple[Chunk, float, int]]:
        if self.index is None:
            raise RetrievalUnavailable("library is not open")
        if not self.chunks:
            return []
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
              focus: dict[str, float] | None = None, relevance="overlap", parts_preset="v0"):
        """Retrieve k chunks, put them back in document order, and run the profile's Equalizer with the
        query as the task. Returns (brief, trace, hits)."""
        from rag_research_agent.rag.profile import Equalizer
        from rag_research_agent.retrieve.semantic_relevance import make_semantic_relevance
        if relevance not in ("overlap", "semantic"):
            raise ValueError("relevance must be overlap or semantic")
        hits = self.search(query, k, mode)
        order = {c.chunk_id: i for i, c in enumerate(self.chunks)}
        draft = "\n\n".join(c.safe_text for c, _, _ in sorted(hits, key=lambda h: order[h[0].chunk_id]))
        overrides = {"relevance": make_semantic_relevance(self.embedder)} if relevance == "semantic" else {}
        brief, trace = Equalizer.from_profile(profile).brief(draft, task=query, budget=budget, focus=focus,
                                                           parts_preset=parts_preset, **overrides)
        return brief, trace, hits


def load_folder(folder: str | Path, patterns: Sequence[str] = ("*.txt", "*.md")) -> list[tuple[str, str, str]]:
    folder = Path(folder)
    docs = []
    for pattern in patterns:
        for f in sorted(folder.glob(pattern)):
            docs.append((f.stem, f.name, f.read_text(encoding="utf-8-sig")))
    return docs
