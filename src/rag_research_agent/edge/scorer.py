"""Rule-based edge scorer v0. Reads everything from a GoldenRules file; no hidden constants.

Scores each segment from the cues it contains and records WHY (matched rule ids), so a person can
look at the result, edit the rules or the golden set, and run again (feedback loop).
Not calibrated: rarity and ontology_priority are 0 until a background corpus and labels exist.
"""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass, field
from typing import Sequence

from rag_research_agent.core.types import Candidate, EdgeScore, Segment
from rag_research_agent.edge.rules import GoldenRules


@dataclass(frozen=True)
class Explanation:
    segment_id: str
    causal_ids: tuple[int, ...] = ()
    pillars: tuple[str, ...] = ()
    packs: tuple[str, ...] = ()
    numbers: int = 0
    cliches: tuple[str, ...] = ()
    protected: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)


def _hits(text: str, cues: Sequence[str]) -> list[str]:
    return [c for c in cues if c and c in text]


class RuleEdgeScorer:
    """Implements the EdgeScorer protocol. Needs the source text because segments hold offsets only."""

    def __init__(self, rules: GoldenRules, source_text: str, packs: Sequence[str] = ()):
        self.rules = rules
        self.text = source_text
        self.packs = tuple(packs)

    def explain_one(self, seg: Segment) -> Explanation:
        t = self.text[seg.start:seg.end]
        causal = tuple(ct.id for ct in self.rules.causal_types if _hits(t, ct.cues))
        protected = any(ct.always_protect for ct in self.rules.causal_types if ct.id in causal)
        pillars = tuple(k for k, cues in self.rules.pillar_cues.items() if _hits(t, cues))
        packs = tuple(p for p in self.packs if _hits(t, self.rules.packs.get(p, ())))
        numbers = sum(len(p.findall(t)) for p in self.rules.number_patterns)
        cliches = tuple(_hits(t, self.rules.cliche_phrases))
        return Explanation(seg.segment_id, causal, pillars, packs, numbers, cliches, protected)

    def score_one(self, seg: Segment) -> EdgeScore:
        e = self.explain_one(seg)
        w = self.rules.weights
        golden = min(1.0, (len(e.pillars) + len(e.packs)) / 2)
        concrete = min(1.0, e.numbers / 2)
        causal = min(1.0, len(e.causal_ids) / 2)
        cliche = 1.0 if e.cliches else 0.0
        total = (w["golden_phrase"] * golden + w["concreteness"] * concrete + w["causal_reversal"] * causal
                 - w["cliche_penalty"] * cliche)
        return EdgeScore(segment_id=seg.segment_id, golden_phrase=golden, concreteness=concrete,
                         causal_reversal=causal, cliche_penalty=cliche, total=max(0.0, round(total, 4)),
                         scorer_version=f"rule-v0:{self.rules.rule_version}")

    def score(self, segments: Sequence[Segment]) -> list[EdgeScore]:
        return [self.score_one(s) for s in segments]


class RuleProtectedPicker:
    """Implements ProtectedPicker: segments matching an always_protect causal type (e.g. 19, 20, 25, 28)."""

    def __init__(self, scorer: RuleEdgeScorer):
        self.scorer = scorer

    def pick(self, segments: Sequence[Segment], scores: Sequence[EdgeScore]) -> list[Candidate]:
        by_id = {s.segment_id: s.total for s in scores}
        return [Candidate(s.segment_id, by_id.get(s.segment_id, 0.0), from_protected_path=True)
                for s in segments if self.scorer.explain_one(s).protected]
