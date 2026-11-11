"""Opt-in immutable Chroma versions; only current.json is replaced.

Publish/activate/prune are single-writer operations (exclusive lock file, fail
fast if busy). Readers snapshot the pointer and keep their original index.
Run prune only after readers of retired versions have finished. A crashed writer
can leave a reserved version and .writer.lock; inspect before removing the lock.
"""
from __future__ import annotations

MATURITY = "incubating"

from contextlib import contextmanager
from dataclasses import asdict
import json
import logging
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from threading import RLock
from typing import Sequence

from rag_research_agent.core.contracts import Chunk
from rag_research_agent.store.chroma_store import ChromaIndex, _client
from rag_research_agent.store.retry import retry_io

LOGGER = logging.getLogger(__name__)
# Chroma's shared-system cache creation and last-owner shutdown are separate
# from its refcount lock. Serialize both across all pointer instances so a new
# reader cannot attach while the last owner is stopping that same system.
_CLIENT_LIFECYCLE = RLock()


class _PointerIndex(ChromaIndex):
    def __init__(self, *args, **kwargs):
        with _CLIENT_LIFECYCLE:
            super().__init__(*args, **kwargs)

    def close(self) -> None:
        with _CLIENT_LIFECYCLE:
            super().close()


class ChromaPointer:
    """Version manager for already masked chunks and caller-supplied vectors.

    Version folders are never moved or overwritten. Failed builds remain reserved
    until explicit pruning. No embedding model or network service is loaded.
    """

    def __init__(self, root: Path):
        self.root = Path(root)

    @contextmanager
    def _writer(self):
        self.root.mkdir(parents=True, exist_ok=True)
        lock = self.root / ".writer.lock"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            raise RuntimeError("CHROMA_WRITER_BUSY") from None
        try:
            os.close(fd)
            yield
        finally:
            lock.unlink()

    def _version_path(self, version: str) -> Path:
        if not isinstance(version, str) or not re.fullmatch(r"v[1-9][0-9]*", version):
            raise ValueError("invalid Chroma version")
        path = self.root / "versions" / version
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError("symlinked version paths are unsupported")
        return path

    def _pointer(self) -> dict:
        with (self.root / "current.json").open(encoding="utf-8") as handle:
            pointer = json.load(handle)
        self._version_path(pointer["version"])
        if pointer.get("previous") is not None:
            self._version_path(pointer["previous"])
        return pointer

    def active_version(self) -> str:
        """Read one complete pointer snapshot without holding a reader lock."""
        return self._pointer()["version"]

    def _replace_pointer(self, version: str) -> None:
        try:
            old = self._pointer()["version"]
        except FileNotFoundError:
            old = None
        fd, name = tempfile.mkstemp(prefix=".current-", suffix=".tmp", dir=self.root)
        temporary = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump({"version": version, "previous": old}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            # Windows readers can briefly deny delete-sharing on current.json.
            # Retry the same complete file; never truncate the live pointer.
            for attempt in range(20):
                try:
                    os.replace(temporary, self.root / "current.json")
                    break
                except PermissionError:
                    if attempt == 19:
                        raise
                    time.sleep(0.01)
        finally:
            temporary.unlink(missing_ok=True)

    def _open(self, version: str) -> ChromaIndex:
        path = self._version_path(version)
        with (path / "manifest.json").open(encoding="utf-8") as handle:
            manifest = json.load(handle)
        index = _PointerIndex(path, manifest["collection"],
                            [Chunk(**item) for item in manifest["chunks"]],
                            manifest["dimension"])
        try:
            index.verify()
        except BaseException:
            index.close()
            raise
        return index

    def open_active(self) -> ChromaIndex:
        """Caller owns close(); later pointer changes do not alter this handle."""
        return self._open(self.active_version())

    def _write_version(self, path: Path, chunks: Sequence[Chunk],
                       vectors: Sequence[Sequence[float]], collection: str,
                       dimension: int) -> None:
        # publish_chroma opens a writer client in addition to the returned index.
        # Own this writer explicitly: an unclosed client keeps HNSW files locked
        # on Windows even after all reader indexes have been closed.
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{1,510}[A-Za-z0-9]", collection):
            raise ValueError("invalid Chroma collection name")
        if len(chunks) != len(vectors):
            raise ValueError("chunks and vectors differ in length")
        if any(len(vector) != dimension for vector in vectors):
            raise ValueError("vector dimension mismatch")
        if len({chunk.chunk_id for chunk in chunks}) != len(chunks):
            raise ValueError("duplicate chunk_id")
        with _CLIENT_LIFECYCLE:
            client = _client(path)
        try:
            col = retry_io(lambda: client.create_collection(
                collection, metadata={"hnsw:space": "cosine", "dimension": dimension}))
            for start in range(0, len(chunks), 64):
                part = chunks[start:start + 64]
                retry_io(lambda: col.add(
                    ids=[chunk.chunk_id for chunk in part],
                    embeddings=[list(map(float, v)) for v in vectors[start:start + 64]],
                    documents=[chunk.safe_text for chunk in part],
                    metadatas=[{"document_id": chunk.document_id,
                                "content_hash": chunk.content_hash} for chunk in part]))
        finally:
            with _CLIENT_LIFECYCLE:
                client.close()

    def publish(self, chunks: Sequence[Chunk], vectors: Sequence[Sequence[float]], *,
                collection: str, dimension: int) -> str:
        """Build and verify a fresh v<N>, then activate it atomically."""
        if dimension <= 0 or not chunks:
            raise ValueError("positive dimension and nonempty chunks required")
        with self._writer():
            versions = self.root / "versions"
            versions.mkdir(exist_ok=True)
            # Permanent empty reservations prevent version ID reuse after prune.
            allocated = self.root / ".allocated"
            allocated.mkdir(exist_ok=True)
            numbers = [int(p.name[1:]) for p in (*versions.iterdir(), *allocated.iterdir())
                       if re.fullmatch(r"v[1-9][0-9]*", p.name)]
            version = f"v{max(numbers, default=0) + 1}"
            path = self._version_path(version)
            (allocated / version).touch(exist_ok=False)
            path.mkdir()  # reservation: never reuse or remove a failed build here
            self._write_version(path, chunks, vectors, collection, dimension)
            with (path / "manifest.json").open("x", encoding="utf-8") as handle:
                json.dump({"collection": collection, "dimension": dimension,
                           "chunks": [asdict(c) for c in chunks]}, handle)
                handle.flush()
                os.fsync(handle.fileno())
            index = self._open(version)
            index.close()
            self._replace_pointer(version)
            return version

    def _activate(self, version: str) -> str:
        index = self._open(version)  # missing/incomplete versions cannot be activated
        index.close()
        if self.active_version() != version:
            self._replace_pointer(version)
        return version

    def activate(self, version: str) -> str:
        with self._writer():
            return self._activate(version)

    def rollback(self) -> str:
        with self._writer():
            previous = self._pointer().get("previous")
            if previous is None:
                raise ValueError("no previous Chroma version")
            return self._activate(previous)

    def prune(self) -> dict[str, list[str]]:
        """Explicit cleanup; active and previous versions are always retained.

        PermissionError (including Windows sharing violations) is a warning.
        Partially removed retired versions can be retried by a later prune.
        """
        with self._writer():
            pointer = self._pointer()
            kept = {pointer["version"], pointer.get("previous")}
            report: dict[str, list[str]] = {"removed": [], "kept_locked": []}
            for path in sorted((self.root / "versions").iterdir()):
                if not re.fullmatch(r"v[1-9][0-9]*", path.name) or path.name in kept:
                    continue
                self._version_path(path.name)
                try:
                    shutil.rmtree(path)
                except PermissionError:
                    LOGGER.warning("CHROMA_PRUNE_LOCKED")
                    report["kept_locked"].append(path.name)
                else:
                    report["removed"].append(path.name)
            return report
