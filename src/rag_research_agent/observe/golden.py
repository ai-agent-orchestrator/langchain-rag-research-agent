"""Golden set loading and checks: questions paired with their answer document IDs.

Evidence questions carry `source` (one ID) or `sources` (several). No-evidence questions carry
`source: null` and are kept in their own file so the 20-question learning set stays unchanged.
The checks catch the mistakes that silently corrupt a comparison: unknown IDs, duplicates,
a split mixing, and too few no-evidence questions to calibrate a gate.
"""
from __future__ import annotations

MATURITY = "incubating"

import json
from pathlib import Path
from typing import Callable, Iterable, Sequence

TYPES = {"paraphrase", "legal_term", "off_topic", "hard_negative"}


class GoldenSetError(ValueError):
    pass


def expected_ids(item: dict) -> list[str]:
    if "sources" in item:
        return list(item["sources"])
    return [] if item.get("source") is None else [item["source"]]


def load(paths: Iterable[Path], document_ids: Iterable[str], *, min_no_evidence: float = 0.0) -> list[dict]:
    known = set(document_ids)
    items: list[dict] = []
    for path in paths:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, list):
            raise GoldenSetError(f"{path}: top level must be a list")
        items.extend(data)
    seen: set[str] = set()
    for pos, item in enumerate(items):
        question = item.get("question", "").strip()
        if not question:
            raise GoldenSetError(f"item {pos}: empty question")
        if question in seen:
            raise GoldenSetError(f"duplicate question: {question}")
        seen.add(question)
        unknown = set(expected_ids(item)) - known
        if unknown:
            raise GoldenSetError(f"{question}: unknown source {sorted(unknown)}")
        if item.get("type") not in TYPES:
            raise GoldenSetError(f"{question}: unknown type {item.get('type')}")
        if not expected_ids(item) and item["type"] not in {"off_topic", "hard_negative"}:
            raise GoldenSetError(f"{question}: a no-evidence question must be off_topic or hard_negative")
    share = sum(not expected_ids(i) for i in items) / len(items) if items else 0.0
    if share < min_no_evidence:
        raise GoldenSetError(f"no-evidence share {share:.2f} is below {min_no_evidence:.2f}")
    return items


def assign_splits(items: Sequence[dict], confirm_every: int = 3) -> list[dict]:
    """Deterministic split when a set has none: every n-th item per (expected, type) group goes to
    confirm, so both splits keep evidence and no-evidence questions. Existing splits are kept."""
    counters: dict[tuple, int] = {}
    out = []
    for item in items:
        if item.get("split"):
            out.append(dict(item))
            continue
        key = (bool(expected_ids(item)), item["type"])
        counters[key] = counters.get(key, 0) + 1
        out.append({**item, "split": "confirm" if counters[key] % confirm_every == 0 else "compare"})
    return out


def to_rows(items: Sequence[dict], rank: Callable[[str], list[tuple[str, float]]], mode: str,
            k: int = 3) -> list[dict]:
    """Turn ranked (document_id, score) lists into evaluate.py rows."""
    rows = []
    for pos, item in enumerate(items, start=1):
        ranked = rank(item["question"])
        scores = [s for _, s in ranked]
        top1 = scores[0] if scores else 0.0
        top2 = scores[1] if len(scores) > 1 else 0.0
        rows.append({"id": item.get("id", f"G{pos:03d}"), "split": item.get("split"), "type": item["type"],
                     "expected": expected_ids(item),
                     mode: {"topk": [d for d, _ in ranked[:k]], "top1": top1, "gap": top1 - top2}})
    return rows
