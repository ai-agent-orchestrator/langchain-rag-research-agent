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


# ---------- two-axis report: "where was the answer ranked" vs "did the gate accept it" ----------
# Ranking and the evidence decision are different questions. A question can be ranked first and
# still be refused by the gate (a false refusal), or be accepted with the wrong document first
# (the dangerous case). Reporting only Hit@k hides both, so each row gets both axes.

OUTCOMES = ("found_accepted", "found_refused", "wrong_accepted", "wrong_refused",
            "no_evidence_refused", "no_evidence_accepted")


def first_hit_rank(row: dict, mode: str) -> int | None:
    """1-based rank of the first expected document, or None when it is not in the list."""
    expected = set(row["expected"])
    for rank, doc in enumerate(row[mode]["topk"], start=1):
        if doc in expected:
            return rank
    return None


def outcome(row: dict, mode: str, rule: dict) -> str:
    accepted = _passes(row, mode, rule)
    if not row["expected"]:
        return "no_evidence_accepted" if accepted else "no_evidence_refused"
    top1_correct = first_hit_rank(row, mode) == 1
    if top1_correct:
        return "found_accepted" if accepted else "found_refused"
    return "wrong_accepted" if accepted else "wrong_refused"


def two_axis_report(rows: Sequence[dict], mode: str, rule: dict, k: int = 3) -> dict:
    """Per-question rank and gate decision plus summary counts. Counts, never bare percentages."""
    per_row = []
    counts = dict.fromkeys(OUTCOMES, 0)
    evidence = [r for r in rows if r["expected"]]
    reciprocal = 0.0
    hit1 = hitk = 0
    for r in rows:
        rank = first_hit_rank(r, mode) if r["expected"] else None
        result = outcome(r, mode, rule)
        counts[result] += 1
        if r["expected"]:
            hit1 += rank == 1
            hitk += rank is not None and rank <= k
            reciprocal += 1 / rank if rank else 0.0
        per_row.append({"id": r["id"], "split": r.get("split"), "type": r.get("type"),
                        "expected": list(r["expected"]), "first_hit_rank": rank,
                        "top1": r[mode]["top1"], "gap": r[mode]["gap"], "outcome": result})
    n = len(evidence)
    return {
        "mode": mode,
        "rule": {key: rule[key] for key in ("tau_abs", "tau_gap") if key in rule} | (
            {"version": rule["version"]} if "version" in rule else {}),
        "ranking": {"hit_at_1": f"{hit1}/{n}", f"hit_at_{k}": f"{hitk}/{n}",
                    "mrr": round(reciprocal / n, 4) if n else None},
        "decision": counts,
        "attention": [p["id"] for p in per_row
                      if p["outcome"] in ("found_refused", "wrong_accepted", "no_evidence_accepted")],
        "rows": per_row,
    }


class FrozenRuleViolation(ValueError):
    """The rule was tuned on rows it is now being confirmed on."""


def freeze_rule(compare_rows: Sequence[dict], mode: str, version: str, use_gap: bool = True) -> dict:
    """Calibrate on the compare split only and record which rows were used."""
    if any(r.get("split") != "compare" for r in compare_rows):
        raise FrozenRuleViolation("calibration accepts compare rows only")
    rule = calibrate(compare_rows, mode, use_gap)
    return {**rule, "mode": mode, "version": version,
            "calibrated_on": sorted(r["id"] for r in compare_rows)}


def confirm(rows: Sequence[dict], rule: dict, k: int = 3) -> dict:
    """Apply a frozen rule once to confirm rows. Refuses rows the rule was calibrated on."""
    if "calibrated_on" not in rule or "version" not in rule:
        raise FrozenRuleViolation("confirm needs a rule from freeze_rule")
    overlap = set(rule["calibrated_on"]) & {r["id"] for r in rows}
    if overlap or any(r.get("split") != "confirm" for r in rows):
        raise FrozenRuleViolation(f"confirm rows must be unseen confirm rows: {sorted(overlap)[:3]}")
    return two_axis_report(rows, rule["mode"], rule, k)
