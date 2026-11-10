"""Empirical cosine thresholds; reuse the existing conservative calibration rule."""
from __future__ import annotations

MATURITY = "incubating"

import math
from statistics import median
from rag_research_agent.observe.evaluate import calibrate, hit_at_k, first_hit_rank, confusion


def summarize_calibration(rows, mode="vector"):
    rows = list(rows)
    for row in rows:
        if any(not math.isfinite(float(row[mode][key])) for key in ("top1", "gap")):
            raise ValueError("non-finite retrieval score")
    evidence = [r for r in rows if r["expected"]]
    correct = [r["correct_score"] for r in evidence if r.get("correct_score") is not None]
    rule = calibrate(rows, mode, use_gap=False) if rows else None
    gaps = sorted(r[mode]["gap"] for r in rows)
    ranks = [first_hit_rank(r, mode) for r in evidence]
    return {"tau_low": min(correct) if correct else None,
            "tau_high": rule["tau_abs"] if rule else None, "rule": rule,
            "no_evidence_count": len(rows) - len(evidence),
            "gap_distribution": {"min": min(gaps), "median": median(gaps), "max": max(gaps)} if gaps else {},
            "hit_at_1": hit_at_k(rows, mode, 1), "hit_at_3": hit_at_k(rows, mode, 3),
            "mrr": sum(1 / rank if rank else 0 for rank in ranks) / len(ranks) if ranks else None,
            "decision": confusion(rows, mode, rule) if rule else {},
            "score_samples": [{"id": r["id"], "correct": r.get("correct_score"),
                               "wrong_max": r.get("wrong_score"),
                               "no_evidence_max": r[mode]["top1"] if not r["expected"] else None} for r in rows],
            "note": "합성 소규모 골든셋, 통계적 결론 아님; 근거 없음 표본이 없으면 오수용 0 보장 불가"}
