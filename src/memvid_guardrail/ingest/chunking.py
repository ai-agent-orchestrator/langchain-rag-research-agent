"""B01: read synthetic guides, split them by heading and token budget, and build Chunk records.

The token counter is injected so that the same code runs with the real E5 tokenizer
(scripts/ingest_guides.py) and with a deterministic fake in tests.
"""
from __future__ import annotations

MATURITY = "incubating"

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from memvid_guardrail.guard.masking import MASKING_VERSION, mask_pii
from memvid_guardrail.core.contracts import Chunk

TokenCounter = Callable[[str], int]


@dataclass(frozen=True)
class GuideDocument:
    document_id: str
    title: str
    case_type: str
    source_version: str
    collection_id: str
    text: str


def load_guides(root: Path) -> list[GuideDocument]:
    manifest = json.loads((root / "guides.json").read_text(encoding="utf-8"))
    docs = []
    for row in manifest["documents"]:
        text = (root / row["file"]).read_text(encoding="utf-8")
        docs.append(GuideDocument(row["documentId"], row["title"], row["caseType"],
                                  manifest["sourceVersion"], manifest["collectionId"], text))
    ids = [d.document_id for d in docs]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate documentId in guides.json")
    return docs


def _sections(text: str) -> list[tuple[str, list[str]]]:
    """Split markdown into (heading, units). Units are bullet lines or sentences."""
    sections: list[tuple[str, list[str]]] = []
    heading, units = "", []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith(">") or stripped.startswith("# "):
            continue  # blank, disclaimer, document title (the title is prefixed to every chunk)
        if stripped.startswith("## "):
            if units:
                sections.append((heading, units))
            heading, units = stripped[3:].strip(), []
            continue
        if stripped.startswith("- "):
            units.append(stripped)
        else:
            units.extend(s for s in re.split(r"(?<=[.!?])\s+", stripped) if s)
    if units:
        sections.append((heading, units))
    return sections


def _hard_split(unit: str, budget: int, count: TokenCounter) -> list[str]:
    """Fallback for a single unit longer than the budget: split on characters."""
    pieces, current = [], ""
    for ch in unit:
        if current and count(current + ch) > budget:
            pieces.append(current)
            current = ""
        current += ch
    if current:
        pieces.append(current)
    return pieces


def split_document(doc: GuideDocument, count: TokenCounter, max_tokens: int = 300,
                   overlap_tokens: int = 40) -> list[tuple[str, int]]:
    """Return (chunk_text, token_count).

    Each chunk starts with the document title. Short sections are packed together up to
    max_tokens; a section heading always stays attached to its first unit, so a heading never
    ends a chunk on its own. Overlap carries trailing whole units (not partial words) of the
    same section, up to overlap_tokens, into the next chunk.
    """
    if not 0 <= overlap_tokens < max_tokens:
        raise ValueError("overlap must be smaller than max_tokens")
    prefix = f"{doc.title}\n"
    budget = max_tokens - count(prefix)
    if budget <= overlap_tokens:
        raise ValueError("title leaves no room for content")
    # Flatten into (section, text) items; the first item of a section carries its heading line.
    items: list[tuple[str, str]] = []
    for heading, units in _sections(doc.text):
        for i, unit in enumerate(units):
            head = f"## {heading}\n" if heading and i == 0 else ""
            pieces = _hard_split(unit, budget - count(head), count) if count(head + unit) > budget else [unit]
            items.extend((heading, (head if j == 0 else "") + piece) for j, piece in enumerate(pieces))

    def render(group: list[tuple[str, str]]) -> str:
        return prefix + "\n".join(text for _, text in group)

    chunks: list[tuple[str, int]] = []
    current: list[tuple[str, str]] = []
    for item in items:
        if current and count(render(current + [item])) > max_tokens:
            body = render(current)
            chunks.append((body, count(body)))
            carry: list[tuple[str, str]] = []
            for prev in reversed(current):
                if prev[0] != item[0] or count("\n".join(t for _, t in [prev] + carry)) > overlap_tokens:
                    break
                carry.insert(0, prev)
            if carry and not carry[0][1].startswith("## "):
                carry[0] = (carry[0][0], f"## {carry[0][0]}\n{carry[0][1]}")  # keep section context
            current = carry if count(render(carry + [item])) <= max_tokens else []
        current.append(item)
    if current:
        body = render(current)
        chunks.append((body, count(body)))
    return chunks


def chunker_version(max_tokens: int, overlap_tokens: int, tokenizer_id: str) -> str:
    return f"heading-unit-v1:{max_tokens}/{overlap_tokens}:{tokenizer_id}"


def build_chunks(docs: list[GuideDocument], count: TokenCounter, tokenizer_id: str,
                 max_tokens: int = 300, overlap_tokens: int = 40, policy_version: str = "unversioned") -> list[Chunk]:
    version = chunker_version(max_tokens, overlap_tokens, tokenizer_id)
    out: list[Chunk] = []
    for doc in docs:
        for index, (text, tokens) in enumerate(split_document(doc, count, max_tokens, overlap_tokens), start=1):
            safe = mask_pii(text)
            if tokens > max_tokens:
                raise ValueError(f"chunk over budget: {doc.document_id} #{index} = {tokens}")
            out.append(Chunk(doc.document_id, f"{doc.document_id}:c{index:02d}:{doc.source_version}",
                             doc.source_version, doc.collection_id, doc.title, safe, tokens,
                             version, MASKING_VERSION, policy_version))
    return out
