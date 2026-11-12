"""Pure retrieval scoring; IDs only, with no model or store dependency."""
from __future__ import annotations

from collections.abc import Iterable

from rag_research_agent.observe.gate_grid import wilson

MATURITY = "incubating"
DEFAULT_KS = (1, 3, 5)


def _ids(values: Iterable[str]) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise ValueError("source IDs must be a collection of nonempty strings")
    result = list(values)
    if any(not isinstance(value, str) or not value for value in result):
        raise ValueError("source IDs must be nonempty strings")
    return result


def score_retrieval(gold_sources, retrieved_ids, ks=DEFAULT_KS):
    """Score one ranking, or return None for absent/empty gold.

    Duplicate results occupy rank positions but never count twice toward recall.
    MRR uses the entire supplied ranking; hit/recall use each requested cutoff.
    """
    ks = tuple(ks)
    if not ks or any(type(k) is not int or k <= 0 for k in ks) or len(set(ks)) != len(ks):
        raise ValueError("ks must contain unique positive integers")
    gold = set(_ids(gold_sources)) if gold_sources is not None else set()
    if not gold:
        return None
    ranked = _ids(retrieved_ids)
    first = next((i for i, sid in enumerate(ranked, 1) if sid in gold), None)
    result = {"n_gold": len(gold), "n_results": len(ranked),
              "mrr": 1 / first if first else 0.0}
    for k in ks:
        found = len(gold.intersection(ranked[:k]))
        result.update({f"hit@{k}": int(found > 0), f"recall@{k}": found / len(gold),
                       f"found@{k}": found})
    return result


def aggregate_retrieval(scores, ks=DEFAULT_KS):
    """Aggregate scored queries, ignoring None (unlabelled queries).

    Hit Wilson intervals use query trials. Recall is micro-averaged over gold
    IDs, with Wilson intervals over query/source pairs (not independent queries).
    MRR is a mean, not a binomial proportion, so has no Wilson interval.
    """
    ks = tuple(ks)
    score_retrieval(None, (), ks)  # validate cutoffs even for an empty aggregate
    rows = [row for row in scores if row is not None]
    n = len(rows)
    result = {"n": n, "mrr": {"n": n, "mean": sum(r["mrr"] for r in rows) / n if n else None}}
    for k in ks:
        for name, numerator, denominator in (
            (f"hit@{k}", sum(r[f"hit@{k}"] for r in rows), n),
            (f"recall@{k}", sum(r[f"found@{k}"] for r in rows), sum(r["n_gold"] for r in rows)),
        ):
            stats = wilson(numerator, denominator)
            stats["ok"] = stats.pop("errors")
            result[name] = stats
    return result
