"""Composition interfaces. M0: protocols and fakes only."""
from __future__ import annotations

MATURITY = "incubating"

from typing import Protocol, Sequence

from rag_research_agent.core.types import Brief, Segment, Status


class Composer(Protocol):
    def compose(self, segments: Sequence[Segment], source_text: str) -> Brief: ...


class OutputChecker(Protocol):
    def check(self, brief: Brief, source_text: str) -> Status: ...


class FakeComposer:
    """Extractive: cuts source text by segment offsets, never writes new text."""
    def compose(self, segments: Sequence[Segment], source_text: str) -> Brief:
        body = "\n".join(source_text[s.start:s.end] for s in segments)
        return Brief(body, Status.OK, tuple(s.segment_id for s in segments))


class FakeOutputChecker:
    def check(self, brief: Brief, source_text: str) -> Status:
        return Status.OK if brief.final_prompt_input in source_text or not brief.final_prompt_input else Status.OUTPUT_REJECTED
