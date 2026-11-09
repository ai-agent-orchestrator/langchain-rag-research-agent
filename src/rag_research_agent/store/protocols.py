"""Vector store interface (memvid adapter lives in memvid_store.py)."""
from __future__ import annotations

MATURITY = "incubating"

from typing import Protocol, Sequence


class VectorStore(Protocol):
    def search_vector(self, query_vector: Sequence[float], k: int = 10): ...
    def search_lex(self, query: str, k: int = 10): ...
    def close(self) -> None: ...


class FakeVectorStore:
    def search_vector(self, query_vector: Sequence[float], k: int = 10):
        return []

    def search_lex(self, query: str, k: int = 10):
        return []

    def close(self) -> None:
        return None
