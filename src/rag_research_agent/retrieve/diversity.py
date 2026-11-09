"""Research-side helpers: near-duplicate grouping, MMR selection under a character budget,
and novelty against already-summarized items. Pure Python on L2-normalized vectors.

These never delete: grouping keeps every member, selection only orders and cuts at a budget,
novelty only reports. Thresholds are calibrated per model and stored with a version.
"""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass
from typing import Sequence


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


@dataclass(frozen=True)
class Item:
    item_id: str
    vector: tuple[float, ...]
    chars: int = 0
    priority: float = 0.0     # e.g. tier x signal; higher first
    protected: bool = False   # e.g. tier S: may lead a group, never dropped from selection


def group_duplicates(items: Sequence[Item], threshold: float) -> list[list[str]]:
    """Mutual-nearest pairs at or above `threshold` join a group (union-find).
    The lead of each group is the highest-priority member (protected first)."""
    parent = {it.item_id: it.item_id for it in items}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    nearest = {}
    for a in items:
        best, best_score = None, -2.0
        for b in items:
            if a.item_id != b.item_id:
                s = dot(a.vector, b.vector)
                if s > best_score:
                    best, best_score = b.item_id, s
        nearest[a.item_id] = (best, best_score)
    for a, (b, score) in nearest.items():
        if b is not None and score >= threshold and nearest.get(b, (None,))[0] == a:
            parent[find(a)] = find(b)
    groups: dict[str, list[Item]] = {}
    for it in items:
        groups.setdefault(find(it.item_id), []).append(it)
    ordered = []
    for members in groups.values():
        members.sort(key=lambda it: (not it.protected, -it.priority, it.item_id))
        ordered.append([m.item_id for m in members])
    return sorted(ordered, key=lambda g: g[0])


def mmr_select(items: Sequence[Item], char_budget: int, diversity: float = 0.3) -> list[str]:
    """Greedy MMR: score = (1 - diversity) * priority - diversity * max similarity to selected.
    Protected items are always selected first (if they fit); nothing is selected past the budget."""
    if not 0.0 <= diversity <= 1.0:
        raise ValueError("diversity must be in [0, 1]")
    chosen: list[Item] = []
    used = 0
    for it in sorted([i for i in items if i.protected], key=lambda i: -i.priority):
        if used + it.chars <= char_budget:
            chosen.append(it)
            used += it.chars
    pool = [i for i in items if not i.protected]
    while pool:
        def score(it):
            redundancy = max((dot(it.vector, c.vector) for c in chosen), default=0.0)
            return (1 - diversity) * it.priority - diversity * redundancy
        best = max(pool, key=lambda it: (score(it), -it.chars, it.item_id))
        pool.remove(best)
        if used + best.chars <= char_budget:
            chosen.append(best)
            used += best.chars
    return [c.item_id for c in chosen]


def is_novel(vector: Sequence[float], seen: Sequence[Sequence[float]], threshold: float) -> bool:
    """True when no already-summarized vector is at or above `threshold` (unsure -> novel)."""
    return all(dot(vector, s) < threshold for s in seen)
