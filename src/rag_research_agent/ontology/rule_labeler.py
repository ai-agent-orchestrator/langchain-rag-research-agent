"""Ontology labeler driven by a filter profile: each domain defines its own classes and cue words.
A segment gets the first class (in profile order) whose cues or patterns match; otherwise Unclassified.
Nothing is ever deleted at labelling time."""
from __future__ import annotations

MATURITY = "incubating"

import re
from dataclasses import dataclass, replace
from typing import Sequence

from rag_research_agent.core.types import Segment

UNCLASSIFIED = "Unclassified"


@dataclass(frozen=True)
class OntologyClass:
    name: str
    cues: tuple[str, ...] = ()
    patterns: tuple[re.Pattern, ...] = ()
    description: str = ""

    def matches(self, text: str) -> bool:
        return any(c and c in text for c in self.cues) or any(p.search(text) for p in self.patterns)


class RuleLabeler:
    """Implements the OntologyLabeler protocol. Needs the source text because segments hold offsets only."""

    def __init__(self, classes: Sequence[OntologyClass], source_text: str = ""):
        names = [c.name for c in classes]
        if len(names) != len(set(names)):
            raise ValueError("duplicate ontology class name")
        self.classes = tuple(classes)
        self.text = source_text

    def with_text(self, source_text: str) -> "RuleLabeler":
        return RuleLabeler(self.classes, source_text)

    def label_text(self, text: str) -> str:
        return next((c.name for c in self.classes if c.matches(text)), UNCLASSIFIED)

    def label(self, segments: Sequence[Segment]) -> list[Segment]:
        out = []
        for s in segments:
            name = self.label_text(self.text[s.start:s.end])
            out.append(replace(s, ontology_label=name, rationale_code=f"rule:{name}"))
        return out


def parse_classes(raw: Sequence[dict]) -> tuple[OntologyClass, ...]:
    return tuple(OntologyClass(c["name"], tuple(c.get("cues", ())), tuple(re.compile(p) for p in c.get("patterns", ())),
                               c.get("description", "")) for c in raw)
