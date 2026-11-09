"""Chunking interface."""
from __future__ import annotations

MATURITY = "incubating"

from typing import Protocol

from rag_research_agent.core.types import Segment


class Chunker(Protocol):
    def split(self, text: str, source: str) -> list[Segment]: ...


class FakeChunker:
    """Splits on blank lines and keeps original offsets."""
    def split(self, text: str, source: str) -> list[Segment]:
        out, pos = [], 0
        for i, part in enumerate(text.split("\n\n")):
            start = text.index(part, pos) if part else pos
            end = start + len(part)
            pos = end
            if part.strip():
                out.append(Segment(f"{source}#{i}", source, start, end))
        return out
