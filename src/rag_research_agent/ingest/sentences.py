"""Sentence chunker v0: splits on sentence-final punctuation / newlines and keeps original offsets."""
from __future__ import annotations

MATURITY = "incubating"

import re

from rag_research_agent.core.types import Segment

_END = re.compile(r"(?<=[.!?。])\s+|\n+")


class SentenceChunker:
    def split(self, text: str, source: str = "draft") -> list[Segment]:
        segs, start = [], 0
        for m in list(_END.finditer(text)) + [None]:
            end = m.start() if m else len(text)
            piece = text[start:end]
            if piece.strip():
                lead = len(piece) - len(piece.lstrip())
                segs.append(Segment(f"s{len(segs) + 1:02d}", source, start + lead, start + len(piece.rstrip())))
            if m:
                start = m.end()
        return segs
