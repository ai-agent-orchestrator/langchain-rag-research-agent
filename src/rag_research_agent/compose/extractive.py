"""Extractive composition and output check (DESIGN 8, F5). The composer only cuts the original text by
offsets; it never writes new sentences. The checker rejects numbers that are not in the source and
segment ids that were not supplied."""
from __future__ import annotations

MATURITY = "incubating"

import re
from typing import Sequence

from rag_research_agent.core.types import Brief, Segment, Status

_NUM = re.compile(r"\d+(?:[.,]\d+)*")
_ID = re.compile(r"(?m)^\[([A-Za-z0-9_#:-]+)\]")   # segment ids only at line start


class ExtractiveComposer:
    """Keeps original order; each line is `[segment_id] original sentence`, inside a DATA block that is
    kept separate from instructions."""

    def compose(self, segments: Sequence[Segment], source_text: str, versions: dict | None = None,
                excluded: Sequence[tuple[str, str]] = (), diet_log: Sequence[str] = (),
                status: Status = Status.OK) -> Brief:
        ordered = sorted(segments, key=lambda s: s.start)
        lines = [f"[{s.segment_id}] {source_text[s.start:s.end]}" for s in ordered]
        body = "<<DATA>>\n" + "\n".join(lines) + "\n<</DATA>>" if lines else ""
        return Brief(body, status, tuple(s.segment_id for s in ordered), tuple(excluded), tuple(diet_log),
                     dict(versions or {}))


class NumberIdOutputChecker:
    def check(self, brief: Brief, source_text: str) -> Status:
        if brief.status is not Status.OK:
            return brief.status
        source_numbers = set(_NUM.findall(source_text))
        body = brief.final_prompt_input
        if any(n not in source_numbers for n in _NUM.findall(_ID.sub("", body))):
            return Status.OUTPUT_REJECTED
        if any(i not in brief.included_ids for i in _ID.findall(body)):
            return Status.OUTPUT_REJECTED
        return Status.OK
