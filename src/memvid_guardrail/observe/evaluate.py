"""Retrieval evaluation helpers: Hit@k on evidence items, no-evidence confusion, calibration.

Rows are plain dicts so any retriever can be evaluated:
  {"id", "split", "type", "expected": [doc ids], <mode>: {"topk": [doc ids], "top1": float, "gap": float}}
Calibration uses the compare split only; the frozen rule is applied once to the confirm split.
"""
from __future__ import annotations

MATURITY = "incubating"

from typing import Sequence


def random_baseline(documents: int, gold: int = 1, k: int = 3) -> dict:
    """Chance that k distinct documents drawn at random include one of `gold` documents."""
    from math import comb
    miss = comb(documents - gold, k) / comb(documents, k) if documents - gold >= k else 0.0
    return {"value": 1 - miss, "assumption": f"{documents} documents, {gold} gold, {k} distinct drawn"}


def hit_at_k(rows: Sequence[dict], mode: str, k: int = 3) -> dict:
    scored = [r for r in rows if r["expected"]]
    by_type: dict[str, list[int]] = {}
    hits = 0
    for r in scored:
        hit = bool(set(r["expected"]) & set(r[mode]["topk"][:k]))
        hits += hit
        cell = by_type.setdefault(r["type"], [0, 0])
        cell[0] += hit
        cell[1] += 1
    return {"hits": hits, "total": len(scored), "by_type": {t: f"{a}/{b}" for t, (a, b) in by_type.items()}}


def _passes(row: dict, mode: str, rule: dict) -> bool:
    return row[mode]["top1"] >= rule["tau_abs"] and row[mode]["gap"] >= rule["tau_gap"]


def confusion(rows: Sequence[dict], mode: str, rule: dict) -> dict:
    out = {"evidence_passed": 0, "evidence_blocked": 0, "no_evidence_passed": 0, "no_evidence_blocked": 0}
    for r in rows:
        key = ("evidence_" if r["expected"] else "no_evidence_") + ("passed" if _passes(r, mode, rule) else "blocked")
        out[key] += 1
    return out


def calibrate(rows: Sequence[dict], mode: str, use_gap: bool = True) -> dict:
    """No no-evidence item may pass; then minimise evidence items gated out; ties go to the
    more conservative (higher) thresholds."""
    tops = sorted({r[mode]["top1"] for r in rows} | {0.0})
    gaps = sorted({r[mode]["gap"] for r in rows} | {0.0}) if use_gap else [0.0]
    best = None
    for tau_abs in tops + [max(tops) + 1e-6]:
        for tau_gap in gaps:
            rule = {"tau_abs": tau_abs, "tau_gap": tau_gap}
            if any(_passes(r, mode, rule) for r in rows if not r["expected"]):
                continue
            false_block = sum(not _passes(r, mode, rule) for r in rows if r["expected"])
            key = (false_block, -tau_abs, -tau_gap)
            if best is None or key < best[0]:
                best = (key, {**rule, "false_block": false_block})
    return best[1]
