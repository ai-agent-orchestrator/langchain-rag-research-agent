"""Pure, opt-in aggregation of METRICS_BOARD run events (no IO or models).

Reasons must already be masked by the event producer. Occurrences, including
repeated codes/reasons, are retained; counts are not counts of unique runs.
Gold labels and injection run IDs are explicit sidecars, not event fields.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Iterable, Mapping

from rag_research_agent.core.run_events import RunEvent

MATURITY = "incubating"


@dataclass(frozen=True)
class GoldEvidence:
    """Unique source IDs at relevance grading, and gold auxiliary evidence.

    Only auxiliary IDs present in docs_in enter the overblocking denominator:
    evidence never retrieved is not a grading failure. docs_kept must be a
    subset of docs_in. Counts must match the associated RunEvent.grade.
    """

    auxiliary_ids: tuple[str, ...]
    docs_in: tuple[str, ...]
    docs_kept: tuple[str, ...]

    def __post_init__(self):
        for name in ("auxiliary_ids", "docs_in", "docs_kept"):
            values = tuple(getattr(self, name))
            if any(not isinstance(value, str) or not value for value in values):
                raise ValueError("gold evidence IDs must be nonempty strings")
            if len(set(values)) != len(values):
                raise ValueError("gold evidence IDs must be unique")
            object.__setattr__(self, name, values)
        if not set(self.docs_kept) <= set(self.docs_in):
            raise ValueError("docs_kept must be a subset of docs_in")


def _ratio(count: int, total: int) -> dict:
    if not total:
        return {"count": count, "total": total, "rate": None, "wilson95": None}
    rate = count / total
    z = 1.959963984540054
    denominator = 1 + z * z / total
    center = (rate + z * z / (2 * total)) / denominator
    radius = z * sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denominator
    return {"count": count, "total": total, "rate": rate,
            "wilson95": [max(0.0, center - radius), min(1.0, center + radius)]}


def aggregate_guard_audit(
    events: Iterable[RunEvent | Mapping], *,
    gold: Mapping[str, GoldEvidence] | None = None,
    injection_run_ids: Iterable[str] = (),
) -> dict[str, dict]:
    """Return domain-keyed grade, guard and overblocking summaries.

    Accept validated RunEvent instances or full schema mappings. Sum document
    counts rather than averaging per-run relevance_drop_rate. Injection runs
    contribute guard occurrences but neither quality denominator. Empty input
    returns {}. A run must appear once (nodes belong inside its run event).
    Missing gold yields rate=None, never a claim of zero overblocking.
    This is a suspicion signal, not a semantic judgement about grader quality.
    """
    gold = {} if gold is None else gold
    injections = set(injection_run_ids)
    domains = {}
    seen = set()
    for item in events:
        event = item if isinstance(item, RunEvent) else RunEvent(**item)
        if event.run_id in seen:
            raise ValueError("duplicate run_id")
        seen.add(event.run_id)
        row = domains.setdefault(event.domain, {
            "runs": 0, "quality_runs": 0, "gold_runs": 0,
            "docs_in": 0, "docs_kept": 0, "guard": {},
            "auxiliary_in": 0, "auxiliary_dropped": 0,
        })
        row["runs"] += 1
        for issue in event.guard:
            bucket = row["guard"].setdefault(issue["code"], {"count": 0, "reason": []})
            bucket["count"] += 1
            bucket["reason"].append(issue["reason"])
        if event.run_id in injections:
            continue
        row["quality_runs"] += 1
        row["docs_in"] += event.grade["docs_in"]
        row["docs_kept"] += event.grade["docs_kept"]
        labels = gold.get(event.run_id)
        if labels is not None:
            if (len(labels.docs_in) != event.grade["docs_in"]
                    or len(labels.docs_kept) != event.grade["docs_kept"]):
                raise ValueError("gold evidence counts must match grade")
            row["gold_runs"] += 1
            eligible = set(labels.auxiliary_ids) & set(labels.docs_in)
            row["auxiliary_in"] += len(eligible)
            row["auxiliary_dropped"] += len(eligible - set(labels.docs_kept))
    return {
        domain: {
            "runs": row["runs"], "quality_runs": row["quality_runs"],
            "grade": {
                "docs_in": row["docs_in"], "docs_kept": row["docs_kept"],
                "relevance_drop_rate": _ratio(row["docs_in"] - row["docs_kept"], row["docs_in"]),
            },
            "guard": row["guard"],
            "overblocking": {"gold_runs": row["gold_runs"],
                             **_ratio(row["auxiliary_dropped"], row["auxiliary_in"])},
        }
        for domain, row in sorted(domains.items())
    }
