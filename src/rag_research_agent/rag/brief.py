"""build_brief v0: wires the Equalizer parts together. Every part is injected through `Parts`, so any
one of them can be replaced (another scorer, mapper, dieter, labeler...) without touching the others.
No LLM call happens here; the output is the extractive brief that a backbone model would receive.
"""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Sequence

from rag_research_agent.compose.extractive import ExtractiveComposer, NumberIdOutputChecker
from rag_research_agent.core.lexical import lex_terms
from rag_research_agent.core.types import Brief, Knobs, Segment, Status
from rag_research_agent.diet.dieter import ClassOrderDieter
from rag_research_agent.edge.rules import GoldenRules, load_rules
from rag_research_agent.edge.scorer import RuleEdgeScorer, RuleProtectedPicker
from rag_research_agent.guard.protocols import FakeInputPolicy
from rag_research_agent.ingest.sentences import SentenceChunker
from rag_research_agent.knobs.mapper import EqualizerConfig, blend, load_config
from rag_research_agent.ontology.protocols import FakeLabeler, FakeLinkBuilder
from rag_research_agent.ontology.link_rules import RuleLinkBuilder

ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RULES = ROOT / "data/golden_rules/research_v1.json"
DEFAULT_CONFIG = ROOT / "data/equalizer/presets_v0.json"


def term_overlap(task: str | None) -> Callable[[str], float]:
    """v0 relevance: share of task terms present in the segment (1.0 when there is no task)."""
    terms = set(lex_terms(task or ""))
    if not terms:
        return lambda _t: 1.0
    return lambda t: round(sum(1 for x in terms if x in t) / len(terms), 4)


@dataclass
class Parts:
    rules: GoldenRules | None = None
    config: EqualizerConfig | None = None
    input_policy: object = field(default_factory=FakeInputPolicy)
    chunker: object = field(default_factory=SentenceChunker)
    labeler: object = field(default_factory=FakeLabeler)
    link_builder: object = field(default_factory=FakeLinkBuilder)
    relevance: Callable[[str | None], Callable[[str], float]] = term_overlap
    scorer_factory: Callable[..., RuleEdgeScorer] = RuleEdgeScorer
    dieter_factory: Callable[..., object] = ClassOrderDieter
    composer: object = field(default_factory=ExtractiveComposer)
    checker: object = field(default_factory=NumberIdOutputChecker)

    @classmethod
    def with_defaults_v1(cls, **overrides):
        """Opt into adjacent causal pairs; legacy construction keeps FakeLinkBuilder."""
        overrides.setdefault("link_builder", RuleLinkBuilder())
        return cls(**overrides)

    def ready(self) -> "Parts":
        self.rules = self.rules or load_rules(DEFAULT_RULES)
        self.config = self.config or load_config(DEFAULT_CONFIG)
        return self


@dataclass
class BriefTrace:
    settings: dict
    rows: list[dict]
    diet_log: list[str]
    status: Status


def build_brief(draft: str, task: str | None = None, knobs: Knobs | None = None, preset: str | None = None,
                budget: int = 600, focus: dict[str, float] | None = None, packs: Sequence[str] | None = None,
                parts: Parts | None = None) -> tuple[Brief, BriefTrace]:
    from rag_research_agent.rag.stages import prepare, STAGES
    state = prepare(parts or Parts(), draft, task, knobs, preset, budget, focus, packs)
    for stage in STAGES:
        state = stage(state, state["parts"])
        if state.get("_finished"):
            break
    return state["brief"], BriefTrace(state["settings"], state["rows"], state["diet_log"], state["status"])
