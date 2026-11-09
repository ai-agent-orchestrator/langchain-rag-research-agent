"""Paragraph chunker for the research library: blank-line paragraphs, long ones split at sentence
boundaries. Produces core `Chunk`s (text kept verbatim). Budget unit is characters in v0."""
from __future__ import annotations

MATURITY = "incubating"

import re

from rag_research_agent.core.contracts import Chunk
from rag_research_agent.ingest.sentences import SentenceChunker

CHUNKER_VERSION = "para-v0"
_BLANK = re.compile(r"\n\s*\n")


def paragraph_chunks(doc_id: str, title: str, text: str, *, max_chars: int = 600, collection_id: str = "library",
                     source_version: str = "v1", masking_version: str = "none", policy_version: str = "none") -> list[Chunk]:
    pieces: list[str] = []
    for para in (p.strip() for p in _BLANK.split(text)):
        if not para:
            continue
        if len(para) <= max_chars:
            pieces.append(para)
            continue
        buf = ""
        for seg in SentenceChunker().split(para):
            sent = para[seg.start:seg.end]
            if buf and len(buf) + 1 + len(sent) > max_chars:
                pieces.append(buf)
                buf = sent
            else:
                buf = f"{buf} {sent}".strip()
        if buf:
            pieces.append(buf)
    return [Chunk(doc_id, f"{doc_id}:p{i:03d}", source_version, collection_id, title, piece, len(piece),
                  f"{CHUNKER_VERSION}:{max_chars}", masking_version, policy_version)
            for i, piece in enumerate(pieces, 1)]
