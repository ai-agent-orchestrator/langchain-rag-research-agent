"""Embedding providers. Documents and queries must share model, revision, dimension and normalization.

E5Embedder follows the multilingual-e5-large-instruct convention as described in this
project's design docs: queries get "Instruct: <task>\\nQuery: <text>", documents get no prefix.
It runs locally only (pinned revision, no remote code). It has NOT been run in the cloud
review workspace: Hugging Face was unreachable there, so real-model behaviour is verified on
the owner's PC (B01 tokenizer, B02b encode).
"""
from __future__ import annotations

MATURITY = "incubating"

import hashlib
import math
import os
import re
import time
from typing import Protocol, Sequence

DEFAULT_TASK = "Given a web search query, retrieve relevant passages that answer the query"
E5_MODEL_ID = "intfloat/multilingual-e5-large-instruct"
E5_MAX_TOKENS = 512


class EmbeddingError(Exception):
    pass


class Embedder(Protocol):
    model_id: str
    revision: str
    dimension: int
    normalization: str

    def encode_documents(self, texts: Sequence[str]) -> list[list[float]]: ...
    def encode_query(self, text: str) -> list[float]: ...
    def count_tokens(self, text: str) -> int: ...


def _check(vectors: list[list[float]], dimension: int) -> list[list[float]]:
    for vec in vectors:
        if len(vec) != dimension or not all(math.isfinite(x) for x in vec):
            raise EmbeddingError("embedding has wrong dimension or non-finite values")
        norm = math.sqrt(sum(x * x for x in vec))
        if not 0.99 <= norm <= 1.01:
            raise EmbeddingError("embedding is not L2-normalized")
    return vectors


class FakeEmbedder:
    """Deterministic character-bigram hashing embedder for tests and dry runs.

    It captures surface overlap only, so it behaves like a keyword method. Results from it
    are never reported as vector-RAG results.
    """
    model_id = "fake-char-bigram"
    revision = "fake-v1"
    normalization = "l2"

    def __init__(self, dimension: int = 1024):
        self.dimension = dimension

    def _embed(self, text: str) -> list[float]:
        vec = [0.0] * self.dimension
        compact = "".join(text.split())
        for i in range(max(len(compact) - 1, 1)):
            gram = compact[i:i + 2]
            slot = int.from_bytes(hashlib.sha256(gram.encode("utf-8")).digest()[:4], "big") % self.dimension
            vec[slot] += 1.0
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return _check([self._embed(t) for t in texts], self.dimension)

    def encode_query(self, text: str) -> list[float]:
        return _check([self._embed(text)], self.dimension)[0]

    def count_tokens(self, text: str) -> int:
        return max(1, len("".join(text.split())) // 2)


class E5Embedder:
    normalization = "l2"
    dimension = 1024
    max_tokens = E5_MAX_TOKENS

    def __init__(self, revision: str, device: str = "cpu", batch_size: int = 8,
                 max_seconds: float = 600.0, task: str = DEFAULT_TASK, model_id: str = E5_MODEL_ID,
                 loader=None):
        if not re.fullmatch(r"[0-9a-fA-F]{40}", revision or ""):
            raise EmbeddingError("pin an exact model revision (commit hash)")
        require_offline()
        self.model_id, self.revision, self.task = model_id, revision, task
        self.batch_size, self.max_seconds = batch_size, max_seconds
        self._model = _load_model(model_id, revision, device, loader)
        self._tokenizer = self._model.tokenizer

    def count_tokens(self, text: str) -> int:
        # Includes special tokens, which also count against the 512 limit.
        return len(self._tokenizer(text, add_special_tokens=True)["input_ids"])

    def query_text(self, text: str) -> str:
        return f"Instruct: {self.task}\nQuery: {text}"

    def _encode(self, texts: list[str]) -> list[list[float]]:
        for t in texts:
            if self.count_tokens(t) > self.max_tokens:
                raise EmbeddingError(f"input exceeds the {self.max_tokens}-token limit; split it first")
        start = time.monotonic()
        out = []
        for i in range(0, len(texts), self.batch_size):
            batch = self._model.encode(texts[i:i + self.batch_size], normalize_embeddings=True,
                                       convert_to_numpy=True, show_progress_bar=False)
            out.extend(row.tolist() for row in batch)
            if time.monotonic() - start > self.max_seconds:
                raise EmbeddingError("encode time limit exceeded")
        return _check(out, self.dimension)

    def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._encode(list(texts))

    def encode_query(self, text: str) -> list[float]:
        return self._encode([self.query_text(text)])[0]


def make_embedder(kind: str, revision: str | None = None, device: str = "cpu",
                  batch_size: int = 8, max_seconds: float = 600.0) -> Embedder:
    if kind == "fake":
        return FakeEmbedder()
    if kind == "e5":
        require_offline()
        return E5Embedder(revision or "", device=device, batch_size=batch_size, max_seconds=max_seconds)
    raise EmbeddingError(f"unknown embedder: {kind}")


def require_offline() -> None:
    """After the one-time pinned download, real runs must load from the local cache only."""
    os.environ.setdefault("HF_HUB_OFFLINE", "1")
    if os.environ.get("HF_HUB_OFFLINE") != "1":
        raise EmbeddingError("set HF_HUB_OFFLINE=1 after the pinned download")


def _load_model(model_id, revision, device, loader=None):
    try:
        if loader is None:
            from sentence_transformers import SentenceTransformer
            loader = SentenceTransformer
        return loader(model_id, revision=revision, device=device, trust_remote_code=False, local_files_only=True)
    except (ImportError, OSError, ValueError) as exc:
        raise EmbeddingError("로컬 모델을 불러올 수 없습니다. embeddings extra 설치 후 scripts/prepare_models.py로 먼저 내려받으세요") from exc


class BgeM3Embedder(E5Embedder):
    """Dense BGE-M3 candidate; normalized vectors, no query/passage prefixes."""
    max_tokens = 8192

    def __init__(self, revision, device="cpu", batch_size=8, max_seconds=600.0, loader=None):
        super().__init__(revision, device, batch_size, max_seconds, model_id="BAAI/bge-m3", loader=loader)

    def query_text(self, text):
        return text
