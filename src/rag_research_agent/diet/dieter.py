"""Token Diet v0 (DESIGN 7-2): remove unprotected segments, lowest score first, class by class,
re-checking the budget after every removal. Never truncates text. Pairs linked by causal links are
removed together or kept together. Reports overflow instead of cutting protected items."""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass, field
from typing import Callable, Sequence

from rag_research_agent.core.types import CausalLink, Segment, Status


def char_units(text: str) -> int:
    """v0 budget unit: characters. Swap for a real tokenizer count later."""
    return len(text)


@dataclass
class DietResult:
    kept: list[Segment]
    removed: list[tuple[str, str]]           # (segment_id, reason)
    log: list[str]
    used: int
    budget: int
    status: Status = Status.OK
    rounds: int = 0
    broken_links: list[tuple[str, str]] = field(default_factory=list)


class ClassOrderDieter:
    def __init__(self, budget: int, class_order: Sequence[str] = ("Unclassified",),
                 never_remove: Sequence[str] = ("Constraint_Guardrail",), count: Callable[[str], int] = char_units):
        self.budget = budget
        self.class_order = tuple(class_order)
        self.never_remove = set(never_remove)
        self.count = count

    def run(self, segments: Sequence[Segment], text: str, scores: dict[str, float],
            protected: set[str], links: Sequence[CausalLink] = ()) -> DietResult:
        kept = list(segments)
        size = {s.segment_id: self.count(text[s.start:s.end]) for s in kept}
        used = sum(size.values())
        res = DietResult(kept, [], [], used, self.budget)
        partners: dict[str, set[str]] = {}
        for l in links:
            partners.setdefault(l.src, set()).add(l.dst)
            partners.setdefault(l.dst, set()).add(l.src)

        def group(sid: str) -> set[str]:
            out, todo = set(), [sid]
            while todo:
                x = todo.pop()
                if x not in out:
                    out.add(x)
                    todo.extend(partners.get(x, ()))
            return out

        order = list(self.class_order) + sorted({s.ontology_label.value for s in kept} - set(self.class_order))
        max_rounds = len(order) + 1
        for label in order:
            if res.used <= self.budget or res.rounds >= max_rounds:
                break
            if label in self.never_remove:
                continue
            res.rounds += 1
            pool = sorted((s for s in res.kept if s.ontology_label.value == label), key=lambda s: (scores.get(s.segment_id, 0.0), -s.start))
            for s in pool:
                if res.used <= self.budget:
                    break
                ids = {x for x in group(s.segment_id) if any(k.segment_id == x for k in res.kept)}
                if ids & protected or any(k.ontology_label.value in self.never_remove for k in res.kept if k.segment_id in ids):
                    continue
                res.kept = [k for k in res.kept if k.segment_id not in ids]
                for x in sorted(ids):
                    res.used -= size[x]
                    reason = f"diet:{label}:score={scores.get(x, 0.0)}" + (":pair" if len(ids) > 1 else "")
                    res.removed.append((x, reason))
                    res.log.append(f"round {res.rounds} removed {x} ({reason}) -> {res.used}/{self.budget}")
        if res.used > self.budget:
            res.status = Status.BUDGET_PROTECTED_OVERFLOW
            res.log.append(f"overflow: {res.used}/{self.budget} with only protected or unremovable items left; nothing truncated")
        return res
