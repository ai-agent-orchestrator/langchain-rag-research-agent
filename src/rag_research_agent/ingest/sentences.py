"""Sentence chunker v0: splits on sentence-final punctuation / newlines and keeps original offsets."""
from __future__ import annotations

MATURITY = "incubating"

import re

from rag_research_agent.core.types import Segment

ABBREVIATIONS = ("u.s.", "u.k.", "e.g.", "i.e.", "dr.", "mr.", "mrs.", "ms.", "inc.", "ltd.", "etc.")
_OPEN = {"(": ")", "[": "]", "{": "}", "“": "”", "‘": "’", '"': '"'}
_PUNCT = ".!?。！？"
_BULLET = re.compile(r"\s*(?:[-•]\s+|\d+\.\s+)")


def _dot_inside(text, index):
    before, after = text[:index + 1], text[index + 1:]
    if any(before.lower().endswith(word) for word in ABBREVIATIONS):
        return True
    if index and text[index - 1].isdigit() and after[:1].isdigit():
        return True
    # Dates with spaces between components, including the final day dot.
    if re.search(r"\b\d{4}\.$", before) and re.match(r"\s*\d{1,2}\.", after):
        return True
    if re.search(r"\b\d{4}\.\s*\d{1,2}\.$", before) and re.match(r"\s*\d{1,2}\.", after):
        return True
    return bool(re.search(r"\b\d{4}\.\s*\d{1,2}\.\s*\d{1,2}\.$", before))


def _ranges(line):
    if _BULLET.match(line):
        return [(0, len(line))]
    ranges, stack, start, i = [], [], 0, 0
    while i < len(line):
        char = line[i]
        if stack and char == stack[-1]:
            stack.pop()
        elif char in _OPEN:
            stack.append(_OPEN[char])
        if char not in _PUNCT or (char == "." and _dot_inside(line, i)):
            i += 1
            continue
        end = i + 1
        while end < len(line) and line[end] in _PUNCT:
            end += 1
        closing = list(stack)
        while closing and end < len(line) and line[end] == closing[-1]:
            closing.pop()
            end += 1
        following = line[end:]
        # Quoted reporting clauses remain in the same sentence; parentheses are internal.
        internal = bool(stack) and (bool(closing) or stack[-1] in (")", "]", "}")
                                    or re.match(r"\s*(?:고|라고|며|라는|는|을|를)\b", following))
        if not internal and (end == len(line) or line[end].isspace()):
            ranges.append((start, end))
            start = end
            stack = closing
            i = end
        else:
            i += 1
    if start < len(line):
        ranges.append((start, len(line)))
    return ranges


class SentenceChunker:
    def split(self, text: str, source: str = "draft") -> list[Segment]:
        segs, offset = [], 0
        for line in text.splitlines(keepends=True):
            content = line.rstrip("\r\n")
            for start, end in _ranges(content):
                piece = content[start:end]
                if piece.strip():
                    lead = len(piece) - len(piece.lstrip())
                    segs.append(Segment(f"s{len(segs) + 1:02d}", source,
                                        offset + start + lead, offset + start + len(piece.rstrip())))
            offset += len(line)
        return segs
