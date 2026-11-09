"""Ontology interfaces. M0: protocols and a fake only; real labelling comes in a later milestone."""
from __future__ import annotations

MATURITY = "incubating"

from typing import Protocol, Sequence

from rag_research_agent.core.types import CausalLink, Segment


class OntologyLabeler(Protocol):
    def label(self, segments: Sequence[Segment]) -> list[Segment]: ...


class LinkBuilder(Protocol):
    def build(self, segments: Sequence[Segment]) -> list[CausalLink]: ...


class FakeLabeler:
    """Returns segments unchanged (label stays Unclassified, which is never deleted)."""
    def label(self, segments: Sequence[Segment]) -> list[Segment]:
        return list(segments)


class FakeLinkBuilder:
    def build(self, segments: Sequence[Segment]) -> list[CausalLink]:
        return []
