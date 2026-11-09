"""Core contracts shared by every module. Pure dataclasses: no model, index or network imports."""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass, field
from enum import StrEnum
from hashlib import sha256



def fingerprint(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


class RetrievalStatus(StrEnum):
    OK = "OK"
    EMPTY = "EMPTY"                      # no usable chunk (none found, or all excluded by checks)
    BELOW_THRESHOLD = "BELOW_THRESHOLD"  # chunks found, but the relevance rule says no evidence


class RetrievalMode(StrEnum):
    LEX = "lex"
    VECTOR = "vector"


class RetrievalUnavailable(Exception):
    """Index or embedder failure. Mapped to 503 RETRIEVAL_UNAVAILABLE, never to 'no evidence'."""
    code = "RETRIEVAL_UNAVAILABLE"


@dataclass(frozen=True)
class Chunk:
    document_id: str
    chunk_id: str
    source_version: str
    collection_id: str
    title: str
    safe_text: str
    token_count: int
    chunker_version: str
    masking_version: str
    policy_version: str
    content_hash: str = ""

    def __post_init__(self):
        if not self.safe_text.strip():
            raise ValueError("empty chunk")
        if self.token_count <= 0:
            raise ValueError("token_count must be positive")
        expected = fingerprint(self.safe_text)
        if self.content_hash and self.content_hash != expected:
            raise ValueError("content_hash does not match safe_text")
        if not self.content_hash:
            object.__setattr__(self, "content_hash", expected)


@dataclass(frozen=True)
class IndexManifest:
    index_version: str
    file: str
    sha256: str
    collection_id: str
    embedding_model: str
    pinned_revision: str
    dimension: int
    normalization: str
    chunker_version: str
    created_at: str
    chunks: tuple[Chunk, ...] = ()

    def __post_init__(self):
        if self.dimension <= 0:
            raise ValueError("dimension must be positive")
        ids = [c.chunk_id for c in self.chunks]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate chunk_id in manifest")

    def chunk(self, chunk_id: str) -> Chunk:
        # memvid returns provenance only as title/frame text; the manifest is the source of truth.
        for item in self.chunks:
            if item.chunk_id == chunk_id:
                return item
        raise KeyError(chunk_id)

    def accepts(self, embedding_model: str, pinned_revision: str, dimension: int, normalization: str) -> bool:
        return (embedding_model, pinned_revision, dimension, normalization) == (
            self.embedding_model, self.pinned_revision, self.dimension, self.normalization)


@dataclass(frozen=True)
class Evidence:
    chunk: Chunk
    mode: RetrievalMode
    score: float
    rank: int
    index_version: str


@dataclass(frozen=True)
class RetrievalResult:
    status: RetrievalStatus
    mode: RetrievalMode
    index_version: str
    evidence: tuple[Evidence, ...] = ()
    excluded_chunk_ids: tuple[str, ...] = field(default=())

    def __post_init__(self):
        if self.status == RetrievalStatus.OK and not self.evidence:
            raise ValueError("OK requires evidence")
        if self.status != RetrievalStatus.OK and self.evidence:
            raise ValueError("only OK may carry evidence")
        if any(e.index_version != self.index_version or e.mode != self.mode for e in self.evidence):
            raise ValueError("evidence from a different index or mode")

    def document_ids(self, k: int = 3) -> tuple[str, ...]:
        """Distinct document IDs in rank order: the unit used for Hit@3."""
        seen: list[str] = []
        for item in sorted(self.evidence, key=lambda e: e.rank):
            if item.chunk.document_id not in seen:
                seen.append(item.chunk.document_id)
        return tuple(seen[:k])

    def cited_subset(self, citation_ids: list[str]) -> bool:
        """True when every cited chunk ID came from this retrieval result."""
        allowed = {e.chunk.chunk_id for e in self.evidence}
        return set(citation_ids) <= allowed


def build_query(case_type: str, core_statement: str, desired_next_step: str | None) -> str:
    """v1 query contract. Inputs are already checked and masked per field; clientName never enters."""
    parts = [case_type, core_statement]
    if desired_next_step:
        parts.append(desired_next_step)
    return "\n".join(parts)
