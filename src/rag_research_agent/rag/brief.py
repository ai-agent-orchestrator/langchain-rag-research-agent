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
    p = (parts or Parts()).ready()
    cfg = p.config
    pre = cfg.presets.get(preset) if preset else None
    if preset and pre is None:
        raise ValueError(f"unknown preset {preset}; available: {sorted(cfg.presets)}")
    knobs = knobs or (pre.knobs if pre else Knobs())
    packs = tuple(packs if packs is not None else (pre.packs if pre else ()))
    if focus is None and pre and pre.focus:
        focus = dict(pre.focus)
    st = cfg.mapper.map(knobs)
    settings = {"preset": preset, "similarity": knobs.similarity, "edge_weight": knobs.edge_weight,
                "threshold": st.threshold, "top_k": st.top_k, "extract_only": st.extract_only,
                "protected_path": st.protected_path, "budget": budget, "packs": list(packs), "focus": focus or {}}
    versions = {"rule_version": p.rules.rule_version, "equalizer": "v0", "mapper": repr(cfg.mapper)}

    decision = p.input_policy.check(draft + "\n" + (task or ""))
    if not decision.allowed:                                   # zero generation calls on a block
        b = Brief("", Status.BLOCKED, versions=versions)
        return b, BriefTrace(settings, [], [f"blocked: {decision.reason}"], Status.BLOCKED)

    labeler = p.labeler.with_text(draft) if hasattr(p.labeler, "with_text") else p.labeler
    segs: list[Segment] = labeler.label(p.chunker.split(draft, "draft"))
    link_builder = p.link_builder.with_text(draft) if hasattr(p.link_builder, "with_text") else p.link_builder
    links = link_builder.build(segs)
    rel_of = p.relevance(task)
    scorer = p.scorer_factory(p.rules, draft, packs, focus=focus)
    edge = {e.segment_id: e for e in scorer.score(segs)}
    rel = {s.segment_id: rel_of(draft[s.start:s.end]) for s in segs}
    final = {s.segment_id: blend(rel[s.segment_id], edge[s.segment_id].total, st.edge_weight) for s in segs}

    ordinary = [s for s in segs if rel[s.segment_id] >= st.threshold]
    ordinary = sorted(ordinary, key=lambda s: (-final[s.segment_id], s.start))[: st.top_k]
    protected_ids: set[str] = set()
    if st.protected_path:
        protected_ids = {c.segment_id for c in RuleProtectedPicker(scorer).pick(segs, list(edge.values()))}
        protected_ids |= {s.segment_id for s in segs if getattr(s.ontology_label, 'value', s.ontology_label) in cfg.never_remove}
    chosen_ids = {s.segment_id for s in ordinary} | protected_ids
    chosen = [s for s in segs if s.segment_id in chosen_ids]
    excluded = [(s.segment_id, "below_threshold" if rel[s.segment_id] < st.threshold else "outside_top_k")
                for s in segs if s.segment_id not in chosen_ids]

    rows = [{"id": s.segment_id, "label": getattr(s.ontology_label, "value", s.ontology_label), "relevance": rel[s.segment_id], "edge": edge[s.segment_id].total,
             "final": final[s.segment_id], "protected": s.segment_id in protected_ids,
             "chosen": s.segment_id in chosen_ids, "text": draft[s.start:s.end]} for s in segs]
    if not chosen:                                             # no evidence: zero generation calls
        b = Brief("", Status.REQUEST_MORE, excluded=tuple(excluded), versions=versions)
        return b, BriefTrace(settings, rows, ["no candidates"], Status.REQUEST_MORE)

    dieter = p.dieter_factory(budget, cfg.class_order, cfg.never_remove)
    diet = dieter.run(chosen, draft, final, protected_ids, links)
    excluded += diet.removed
    for r in rows:
        r["kept"] = any(k.segment_id == r["id"] for k in diet.kept)
    brief = p.composer.compose(diet.kept, draft, versions, excluded, diet.log, diet.status)
    status = p.checker.check(brief, draft)
    if status is not brief.status:
        brief = Brief("", status, brief.included_ids, brief.excluded, brief.diet_log, brief.versions)
    return brief, BriefTrace(settings, rows, diet.log, status)
