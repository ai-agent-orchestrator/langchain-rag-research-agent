"""memvid index with externally computed vectors and an atomic active pointer.

Rules enforced here:
- memvid telemetry is forced off before import and verified off.
- every stored record passes enable_embedding=False; memvid never computes or sends embeddings.
- provenance comes from our manifest (title == chunk_id), never from memvid metadata,
  because memvid folds metadata into the searchable text.
- index files are immutable per version; activation swaps only the small pointer file.
- any memvid or integrity failure is RetrievalUnavailable, never "no evidence".
"""
from __future__ import annotations

MATURITY = "incubating"

import hashlib
import json
import os
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence

from memvid_guardrail.core.contracts import Chunk, IndexManifest, RetrievalUnavailable
from memvid_guardrail.retrieve.keyword import lex_terms

POINTER = "active.json"
PUT_BATCH = 8


def load_memvid():
    os.environ["MEMVID_TELEMETRY"] = "0"
    try:
        import memvid_sdk
    except ImportError as exc:  # no silent fallback to another store
        raise RetrievalUnavailable("memvid-sdk is not installed") from exc
    if memvid_sdk.is_telemetry_enabled():
        raise RetrievalUnavailable("memvid telemetry could not be disabled")
    return memvid_sdk


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _manifest_to_json(manifest: IndexManifest) -> dict:
    data = asdict(manifest)
    data["chunks"] = [asdict(c) for c in manifest.chunks]
    return data


def _manifest_from_json(data: dict) -> IndexManifest:
    chunks = tuple(Chunk(**c) for c in data.pop("chunks"))
    return IndexManifest(**data, chunks=chunks)


def publish_index(chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]], *, index_dir: Path,
                  index_version: str, embedding_model: str, pinned_revision: str,
                  dimension: int, normalization: str = "l2") -> IndexManifest:
    """Write <index_version>.mv2 and its manifest, verify them, then swap active.json."""
    if len(chunks) != len(vectors) or not chunks:
        raise ValueError("chunks and vectors must be non-empty and the same length")
    if any(len(v) != dimension for v in vectors):
        raise ValueError("vector dimension mismatch")
    collections = {c.collection_id for c in chunks}
    chunker_versions = {c.chunker_version for c in chunks}
    if len(collections) != 1 or len(chunker_versions) != 1:
        raise ValueError("one index holds one collection and one chunker version")
    index_dir.mkdir(parents=True, exist_ok=True)
    mv2 = index_dir / f"{index_version}.mv2"
    meta = index_dir / f"{index_version}.manifest.json"
    if mv2.exists() or meta.exists():
        raise FileExistsError(f"index version already exists: {index_version}")
    memvid = load_memvid()
    requests = [{"title": c.chunk_id, "label": "guide", "text": c.safe_text, "metadata": {},
                 "enable_embedding": False} for c in chunks]
    identity = {"provider": "external", "model": embedding_model, "dimension": dimension,
                "normalized": normalization == "l2"}
    try:
        mem = memvid.use("basic", str(mv2), mode="auto", enable_vec=True, enable_lex=True)
        try:
            # memvid-sdk 2.0.160 silently drops vectors from large put_many calls (observed with
            # 30+ items per call). Small batches kept every vector in our probe; the full check
            # below still verifies every chunk before activation.
            for start in range(0, len(requests), PUT_BATCH):
                mem.put_many(requests[start:start + PUT_BATCH],
                             embeddings=[list(map(float, v)) for v in vectors[start:start + PUT_BATCH]],
                             embedding_identity=identity)
            mem.seal()
        finally:
            mem.close()
    except Exception as exc:
        raise RetrievalUnavailable(f"memvid write failed: {type(exc).__name__}") from exc
    manifest = IndexManifest(index_version, mv2.name, _sha256(mv2), collections.pop(), embedding_model,
                             pinned_revision, dimension, normalization, chunker_versions.pop(),
                             datetime.now(timezone.utc).isoformat(timespec="seconds"), tuple(chunks))
    meta.write_text(json.dumps(_manifest_to_json(manifest), ensure_ascii=False, indent=1), encoding="utf-8")
    # Verify the sealed, reopened file before activation: every chunk must be searchable and
    # must come first for its own vector. A failure leaves the previous active index in place.
    index = MemvidIndex(index_dir, manifest)
    try:
        if index.vector_count(vectors[0]) != len(chunks):
            raise RetrievalUnavailable("vector index is missing chunks")
        for vector, chunk in zip(vectors, chunks):
            top = index.search_vector(vector, k=1)
            if not top or top[0][0].chunk_id != chunk.chunk_id:
                raise RetrievalUnavailable(f"self-retrieval check failed for {chunk.chunk_id}")
    finally:
        index.close()
    _write_pointer(index_dir, manifest, meta.name)
    return manifest


def _read_pointer(index_dir: Path) -> dict | None:
    try:
        return json.loads((index_dir / POINTER).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as exc:
        raise RetrievalUnavailable("active index pointer unreadable") from exc


def _write_pointer(index_dir: Path, manifest: IndexManifest, manifest_name: str) -> None:
    current = _read_pointer(index_dir)
    previous = current.get("indexVersion") if current else None
    pointer = {"indexVersion": manifest.index_version, "file": manifest.file, "manifest": manifest_name,
               "sha256": manifest.sha256,
               "previous": previous if previous != manifest.index_version else current.get("previous")}
    tmp = index_dir / (POINTER + ".tmp")
    tmp.write_text(json.dumps(pointer, indent=1), encoding="utf-8")
    os.replace(tmp, index_dir / POINTER)  # only the pointer is swapped; open .mv2 files are untouched


def list_versions(index_dir: Path) -> list[dict]:
    """Every published version with its state: active, previous, or retired (oldest first)."""
    pointer = _read_pointer(index_dir) or {}
    out = []
    for meta in sorted(index_dir.glob("*.manifest.json")):
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            out.append({"indexVersion": meta.name.removesuffix(".manifest.json"), "state": "unreadable"})
            continue
        version = data["index_version"]
        state = ("active" if version == pointer.get("indexVersion") else
                 "previous" if version == pointer.get("previous") else "retired")
        out.append({"indexVersion": version, "state": state, "createdAt": data["created_at"],
                    "embeddingModel": data["embedding_model"], "chunks": len(data["chunks"])})
    return sorted(out, key=lambda v: v.get("createdAt", ""))


def activate(index_dir: Path, index_version: str, *, embedding_model: str, pinned_revision: str,
             dimension: int, normalization: str = "l2") -> IndexManifest:
    """Point active.json at an existing version (rollback or roll forward) after re-checking it.

    The version must still match its manifest hash and the caller's embedder identity, and must
    reopen read-only. Nothing is rewritten; a failed check leaves the current pointer alone.
    """
    meta = index_dir / f"{index_version}.manifest.json"
    try:
        manifest = _manifest_from_json(json.loads(meta.read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RetrievalUnavailable(f"manifest unreadable for {index_version}") from exc
    mv2 = index_dir / manifest.file
    if not mv2.exists() or _sha256(mv2) != manifest.sha256:
        raise RetrievalUnavailable("index file does not match its manifest")
    if not manifest.accepts(embedding_model, pinned_revision, dimension, normalization):
        raise RetrievalUnavailable("query embedder does not match the index")
    MemvidIndex(index_dir, manifest).close()
    _write_pointer(index_dir, manifest, meta.name)
    return manifest


def prune(index_dir: Path) -> dict:
    """Delete retired versions; keep the active one and the previous one for rollback.

    Windows refuses to delete a file another process still has open. Such files are reported in
    `kept_locked` and left in place, never forced, so a later prune can finish the job.
    """
    removed, locked = [], []
    for item in list_versions(index_dir):
        if item["state"] != "retired":
            continue
        version = item["indexVersion"]
        paths = [index_dir / f"{version}.mv2", *index_dir.glob(f"{version}.mv2.*"),
                 index_dir / f"{version}.manifest.json"]
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except PermissionError:
                locked.append(path.name)
        removed.append(version)
    return {"removed": removed, "kept_locked": locked}


def open_active(index_dir: Path, *, embedding_model: str, pinned_revision: str, dimension: int,
                normalization: str = "l2") -> "MemvidIndex":
    try:
        pointer = json.loads((index_dir / POINTER).read_text(encoding="utf-8"))
        manifest = _manifest_from_json(json.loads((index_dir / pointer["manifest"]).read_text(encoding="utf-8")))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RetrievalUnavailable("active index pointer or manifest unreadable") from exc
    mv2 = index_dir / manifest.file
    # A hash detects change against the trusted manifest; it does not prove the content is safe.
    if pointer.get("sha256") != manifest.sha256 or not mv2.exists() or _sha256(mv2) != manifest.sha256:
        raise RetrievalUnavailable("index file does not match its manifest")
    if not manifest.accepts(embedding_model, pinned_revision, dimension, normalization):
        raise RetrievalUnavailable("query embedder does not match the index")
    return MemvidIndex(index_dir, manifest)


class MemvidIndex:
    def __init__(self, index_dir: Path, manifest: IndexManifest):
        self.manifest = manifest
        self._by_id = {c.chunk_id: c for c in manifest.chunks}
        memvid = load_memvid()
        try:
            self._mem = memvid.use("basic", str(index_dir / manifest.file), mode="open",
                                   enable_vec=True, enable_lex=True, read_only=True)
        except Exception as exc:
            raise RetrievalUnavailable(f"memvid open failed: {type(exc).__name__}") from exc

    def _hits(self, result) -> list[tuple[Chunk, float, int]]:
        out = []
        for hit in result["hits"]:
            chunk = self._by_id.get(hit.get("title"))
            if chunk is None:
                raise RetrievalUnavailable("index returned a chunk missing from the manifest")
            out.append((chunk, float(hit["score"]), int(hit["rank"])))
        return out

    def search_vector(self, query_vector: Sequence[float], k: int = 10) -> list[tuple[Chunk, float, int]]:
        if len(query_vector) != self.manifest.dimension:
            raise RetrievalUnavailable("query vector dimension mismatch")
        try:
            result = self._mem.find("", k=k, mode="sem", query_embedding=list(map(float, query_vector)))
        except Exception as exc:
            raise RetrievalUnavailable(f"vector search failed: {type(exc).__name__}") from exc
        return self._hits(result)

    def vector_count(self, any_vector: Sequence[float]) -> int:
        """Number of chunks reachable through vector search (total_hits for k = all chunks)."""
        try:
            result = self._mem.find("", k=len(self._by_id), mode="sem",
                                    query_embedding=list(map(float, any_vector)))
        except Exception as exc:
            raise RetrievalUnavailable(f"vector search failed: {type(exc).__name__}") from exc
        return int(result.get("total_hits", len(result["hits"])))

    def search_lex(self, query: str, k: int = 10) -> list[tuple[Chunk, float, int]]:
        # memvid lex requires every term by default (a full intake sentence returns nothing),
        # so the keyword baseline ORs the whitespace terms. No Korean morphology: "반환이" does
        # not match "반환". That limitation is part of what the comparison should show.
        terms = lex_terms(query)
        if not terms:
            return []
        try:
            result = self._mem.find(" OR ".join(terms), k=k, mode="lex")
        except Exception as exc:
            raise RetrievalUnavailable(f"keyword search failed: {type(exc).__name__}") from exc
        return self._hits(result)

    def close(self) -> None:
        try:
            self._mem.close()
        except Exception:
            pass
