"""Data shapes for the division-of-labour research graph (docs/RESEARCH_GRAPH_DESIGN.ko.md 2).

Every claim and metric carries the id of its source and the character span it was cut from, so
anything in the final report can be traced back, and an invented quote fails span_matches().
"""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass, field
from typing import Literal

Stance = Literal["pro", "con", "neutral"]
Kind = Literal["causal", "constraint", "fact", "claim"]
NO_COUNTER_EVIDENCE = "반대·리스크 근거를 찾지 못했습니다(로컬 자료 기준)."


@dataclass(frozen=True)
class SourceRef:
    source_id: str
    text: str                     # masked text, never sent anywhere; spans index into it
    branch: str = "base"          # retrieval branch that found it: base / pro / con / gap:<metric>
    score: float = 0.0


@dataclass(frozen=True)
class Claim:
    claim_id: str
    source_id: str
    start: int
    end: int
    text: str
    stance: Stance = "neutral"
    kind: Kind = "claim"


@dataclass(frozen=True)
class Metric:
    name: str                     # required-metric term it was matched to ("" if none)
    value: str                    # verbatim, never calculated
    unit: str
    claim_id: str
    source_id: str


@dataclass(frozen=True)
class Relation:
    kind: Literal["causes", "contradicts", "condition"]
    src: str                      # claim ids
    dst: str
    source_id: str = ""


@dataclass(frozen=True)
class ResearchPlan:
    required_metrics: tuple[str, ...]
    origin: tuple[tuple[str, str], ...] = ()   # (metric, "auto" | "checklist")
    perspectives: tuple[str, ...] = ("base", "pro", "con")


@dataclass(frozen=True)
class ReportSentence:
    text: str
    claim_ids: tuple[str, ...] = ()
    note: bool = False            # system note (e.g. "no counter evidence"), not a finding


@dataclass(frozen=True)
class Draft:
    sentences: tuple[ReportSentence, ...] = field(default_factory=tuple)

    def render(self) -> str:
        return " ".join(s.text + ("" if not s.claim_ids else " [" + ",".join(s.claim_ids) + "]")
                        for s in self.sentences)

    def body(self) -> str:
        return " ".join(s.text for s in self.sentences if not s.note)


def span_matches(claim: Claim, sources: dict[str, SourceRef]) -> bool:
    source = sources.get(claim.source_id)
    return source is not None and 0 <= claim.start < claim.end <= len(source.text) \
        and source.text[claim.start:claim.end] == claim.text
