"""M0 contract types for the Equalizer pipeline (DESIGN.ko.md section 4). Stdlib only; no behaviour."""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass, field
from enum import StrEnum


class Status(StrEnum):
    OK = "OK"
    BLOCKED = "BLOCKED"                                    # input policy block, zero generation calls
    REQUEST_MORE = "REQUEST_MORE"                          # not enough evidence, zero generation calls
    BUDGET_PROTECTED_OVERFLOW = "BUDGET_PROTECTED_OVERFLOW"  # protected items alone exceed budget, never truncate
    OUTPUT_REJECTED = "OUTPUT_REJECTED"                    # output check failed, result discarded


class OntologyLabel(StrEnum):
    CORE = "Core"
    MARKET = "Market"
    TECH = "Tech"
    ACTION = "Action"
    CONSTRAINT_GUARDRAIL = "Constraint_Guardrail"
    UNCLASSIFIED = "Unclassified"                          # never deleted at labelling time


class LinkType(StrEnum):
    CAUSES = "causes"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"


@dataclass(frozen=True)
class Segment:
    segment_id: str
    source: str
    start: int                    # offsets into the original text; the LLM never writes body text
    end: int
    parent_segment_id: str | None = None
    text_ref: str = ""
    ontology_label: OntologyLabel = OntologyLabel.UNCLASSIFIED
    confidence: float = 0.0
    rationale_code: str = ""

    def __post_init__(self):
        if self.start < 0 or self.end < self.start:
            raise ValueError("invalid offsets")


@dataclass(frozen=True)
class Knobs:
    similarity: float = 0.5       # knob 1, spear: 0 broad .. 1 precise
    edge_weight: float = 0.5      # knob 2, shield: 0 relevance only .. 1 edge only

    def __post_init__(self):
        for name in ("similarity", "edge_weight"):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be within 0..1")


@dataclass(frozen=True)
class Candidate:
    segment_id: str
    relevance: float
    from_protected_path: bool = False


@dataclass(frozen=True)
class EdgeScore:
    segment_id: str
    rarity: float = 0.0
    golden_phrase: float = 0.0
    concreteness: float = 0.0
    causal_reversal: float = 0.0
    ontology_priority: float = 0.0
    cliche_penalty: float = 0.0
    total: float = 0.0
    scorer_version: str = ""


@dataclass(frozen=True)
class CausalLink:
    src: str
    dst: str
    type: LinkType
    origin: str = "rule"          # rule | model_review


@dataclass(frozen=True)
class Brief:
    final_prompt_input: str
    status: Status
    included_ids: tuple[str, ...] = ()
    excluded: tuple[tuple[str, str], ...] = ()   # (segment_id, reason)
    diet_log: tuple[str, ...] = ()
    versions: dict[str, str] = field(default_factory=dict)
