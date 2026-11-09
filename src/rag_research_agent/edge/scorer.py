"""Rule-based edge scorer v0. Reads everything from a GoldenRules file; no hidden constants.

Scores each segment from the cues it contains and records WHY (matched rule ids), so a person can
look at the result, edit the rules or the golden set, and run again (feedback loop).
Not calibrated: rarity and ontology_priority are 0 until a background corpus and labels exist.
"""
from __future__ import annotations

MATURITY = "incubating"

import re
from dataclasses import dataclass, field
from typing import Sequence

from rag_research_agent.core.types import Candidate, EdgeScore, Segment
from rag_research_agent.edge.rules import GoldenRules


@dataclass(frozen=True)
class Explanation:
    segment_id: str
    causal_ids: tuple[int, ...] = ()
    pillars: tuple[str, ...] = ()      # matched rule ids, e.g. R2, T4, N6, A1
    packs: tuple[str, ...] = ()        # matched pack rule ids, e.g. M3, G2, K5
    numbers: int = 0
    cliches: tuple[str, ...] = ()      # matched cliche rule ids, e.g. X7
    protected: bool = False
    has_content: bool = False          # any causal / pillar / pack / number signal
    focus: tuple[str, ...] = ()        # focus keywords found in the segment
    boosts: tuple[str, ...] = ()       # matched weight rule ids, e.g. W1, W5
    notes: tuple[str, ...] = field(default_factory=tuple)


_PARTICLE_TAIL = "(?:은|는|이|가|을|를|의|에|에서|에게|으로|로|와|과|도|만|까지|부터|보다|처럼|측|씨)?"


def keyword_pattern(keyword: str) -> re.Pattern:
    """Match a keyword as a word: not glued to a preceding letter, optionally followed by a particle."""
    return re.compile(r"(?<![가-힣A-Za-z0-9])" + re.escape(keyword) + _PARTICLE_TAIL + r"(?![가-힣A-Za-z0-9])")


def _hits(text: str, cues: Sequence[str]) -> list[str]:
    return [c for c in cues if c and c in text]


class RuleEdgeScorer:
    """Implements the EdgeScorer protocol. Needs the source text because segments hold offsets only."""

    MAX_FOCUS = 5

    def __init__(self, rules: GoldenRules, source_text: str, packs: Sequence[str] = (),
                 focus: dict[str, float] | None = None, focus_weight: float = 0.5):
        """focus: up to 5 keywords -> relative weight (1.0 = normal). Segments with a focus keyword get
        focus_weight * (sum of their keyword weights, capped at 1) added to the total."""
        focus = dict(focus or {})
        if len(focus) > self.MAX_FOCUS:
            raise ValueError(f"at most {self.MAX_FOCUS} focus keywords (got {len(focus)})")
        if any(w <= 0 for w in focus.values()):
            raise ValueError("focus weights must be positive")
        self.focus = focus
        self.focus_weight = focus_weight
        self._focus_re = {k: keyword_pattern(k) for k in focus}
        unknown = [p for p in packs if p not in rules.packs]
        if unknown:
            raise ValueError(f"unknown packs {unknown}; available: {sorted(rules.packs)}")
        self.rules = rules
        self.text = source_text
        self.packs = tuple(packs)

    def explain_one(self, seg: Segment) -> Explanation:
        t = self.text[seg.start:seg.end]
        causal = tuple(ct.id for ct in self.rules.causal_types if _hits(t, ct.cues))
        protected = any(ct.always_protect for ct in self.rules.causal_types if ct.id in causal)
        pillars = tuple(r.id for r in self.rules.pillar_rules if r.matches(t))
        packs = tuple(r.id for p in self.packs for r in self.rules.packs.get(p, ()) if r.matches(t))
        numbers = sum(len(p.findall(t)) for p in self.rules.number_patterns)
        cliches = tuple(r.id for r in self.rules.cliche_rules if r.matches(t))
        protected = protected or any(r.always_protect for r in self.rules.pillar_rules if r.id in pillars)
        has_content = bool(causal or pillars or packs or numbers)
        focus = tuple(k for k, rx in self._focus_re.items() if rx.search(t))
        boosts = tuple(r.id for r in self.rules.weight_rules if r.matches(t))
        return Explanation(seg.segment_id, causal, pillars, packs, numbers, cliches, protected, has_content,
                           focus, boosts)

    def score_one(self, seg: Segment) -> EdgeScore:
        e = self.explain_one(seg)
        w = self.rules.weights
        golden = min(1.0, (len(e.pillars) + len(e.packs)) / 4)
        concrete = min(1.0, e.numbers / 2)
        causal = min(1.0, len(e.causal_ids) / 2)
        # Context is not decided by wording alone: a cliche phrase next to real content is flagged, not penalized.
        cliche = 1.0 if e.cliches and not (self.rules.penalize_cliche_only_without_content and e.has_content) else 0.0
        focus = min(1.0, sum(self.focus[k] for k in e.focus)) if e.focus else 0.0
        by_id = {r.id: r.weight for r in self.rules.weight_rules}
        boost = min(1.0, sum(by_id[i] for i in e.boosts) / 2) if e.boosts else 0.0
        total = (self.focus_weight * focus + w.get("boost", 0.0) * boost + w["golden_phrase"] * golden + w["concreteness"] * concrete + w["causal_reversal"] * causal
                 - w["cliche_penalty"] * cliche)
        return EdgeScore(segment_id=seg.segment_id, golden_phrase=golden, concreteness=concrete,
                         causal_reversal=causal, cliche_penalty=cliche, total=max(0.0, round(total, 4)),
                         scorer_version=f"rule-v0:{self.rules.rule_version}")

    def score(self, segments: Sequence[Segment]) -> list[EdgeScore]:
        return [self.score_one(s) for s in segments]


def focus_brief(scorer: RuleEdgeScorer, segments: Sequence[Segment]) -> dict:
    """Extractive focus view: focus segments in original order (keywords marked), always-protected
    segments kept as short caveats, everything else omitted BUT listed (never silently dropped)."""
    out = {"focus": [], "caveats": [], "omitted": []}
    for s in segments:
        e = scorer.explain_one(s)
        text = scorer.text[s.start:s.end]
        if e.focus:
            for k in sorted(e.focus, key=len, reverse=True):
                rx = re.compile(r"(?<![가-힣A-Za-z0-9*])" + re.escape(k) + r"(?=" + _PARTICLE_TAIL + r"(?![가-힣A-Za-z0-9]))")
                text = rx.sub(lambda m: f"**{m.group(0)}**", text)
            out["focus"].append((s.segment_id, text, e.focus))
        elif e.protected:
            out["caveats"].append((s.segment_id, text))
        else:
            out["omitted"].append(s.segment_id)
    return out


class RuleProtectedPicker:
    """Implements ProtectedPicker: segments matching an always_protect causal type (e.g. 19, 20, 25, 28)."""

    def __init__(self, scorer: RuleEdgeScorer):
        self.scorer = scorer

    def pick(self, segments: Sequence[Segment], scores: Sequence[EdgeScore]) -> list[Candidate]:
        by_id = {s.segment_id: s.total for s in scores}
        return [Candidate(s.segment_id, by_id.get(s.segment_id, 0.0), from_protected_path=True)
                for s in segments if self.scorer.explain_one(s).protected]
