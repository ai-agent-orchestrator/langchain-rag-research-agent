"""Opt-in, per-run target checks using the METRICS_BOARD event field names.

Targets are domain-keyed objects with min/max bounds, e.g.
{"research": {"cost_krw": {"max": 1.5}}}. Grade bounds live under
grade.relevance_drop_rate; guard bounds count all guard occurrences.
No settings are loaded and no existing pipeline is changed on import.
"""
from __future__ import annotations

import json
from math import isclose, isfinite
from pathlib import Path
from typing import Iterable, Mapping

from rag_research_agent.core.run_events import RunEvent
from rag_research_agent.rag.guard_audit import aggregate_guard_audit

MATURITY = "incubating"


def load_targets(path: str | Path = "evals/metric_targets.json") -> dict:
    """Read an explicit local target file; a missing file disables warnings.

    Malformed JSON, invalid target values and permission errors are not hidden.
    The default path is relative to the caller's working directory.
    """
    try:
        with Path(path).open(encoding="utf-8") as stream:
            targets = json.load(stream)
    except FileNotFoundError:
        return {}
    _validate(targets)
    return targets


def _bounds(row):
    return (("cost_krw", row.get("cost_krw", {})),
            ("total_ms", row.get("total_ms", {})),
            ("grade.relevance_drop_rate", row.get("grade", {}).get("relevance_drop_rate", {})),
            ("guard", row.get("guard", {})))


def _validate(targets):
    if not isinstance(targets, Mapping):
        raise ValueError("targets must be a domain-keyed object")
    for domain, row in targets.items():
        if not isinstance(domain, str) or not isinstance(row, Mapping):
            raise ValueError("target domains must map to objects")
        if not isinstance(row.get("grade", {}), Mapping):
            raise ValueError("grade targets must be an object")
        for metric, bounds in _bounds(row):
            if not isinstance(bounds, Mapping) or set(bounds) - {"min", "max"}:
                raise ValueError("metric bounds must contain only min/max")
            for value in bounds.values():
                if type(value) not in (int, float) or not isfinite(value) or value < 0:
                    raise ValueError("bounds must be finite nonnegative numbers")
                if metric == "grade.relevance_drop_rate" and value > 1:
                    raise ValueError("rate bounds must be within zero and one")
                if metric == "guard" and type(value) is not int:
                    raise ValueError("guard bounds must be integer counts")
            if "min" in bounds and "max" in bounds and bounds["min"] > bounds["max"]:
                raise ValueError("minimum must not exceed maximum")


def check_targets(
    events: Iterable[RunEvent | Mapping], targets: Mapping | str | Path, *,
    injection_run_ids: Iterable[str] = (),
) -> list[dict]:
    """Return each out-of-range metric, preserving event order; equality passes.

    Accept actual RunEvents or complete schema mappings, and loaded targets or
    a file path. Missing domains/metrics/bounds are disabled, with no fallback.
    Each warning carries run_id, domain, estimated, metric, value, bound, limit.
    Drop-rate warnings also carry count/total/rate/wilson95. Injection run IDs
    skip only relevance checks. Empty document samples have no measured rate.
    Guard counts are conservative rejection signals, not proven unsafe output;
    reasons and spans are never copied into warnings. No logging or writes.
    """
    targets = load_targets(targets) if isinstance(targets, (str, Path)) else targets
    _validate(targets)
    if not targets:
        return []
    injections, seen, warnings = set(injection_run_ids), set(), []
    for item in events:
        event = item if isinstance(item, RunEvent) else RunEvent(**item)
        if event.run_id in seen:
            raise ValueError("duplicate run_id")
        seen.add(event.run_id)
        row = targets.get(event.domain, {})
        for metric, bounds in _bounds(row):
            if not bounds:
                continue
            ratio = None
            if metric == "grade.relevance_drop_rate":
                if event.run_id in injections or not event.grade["docs_in"]:
                    continue
                ratio = aggregate_guard_audit([event])[event.domain]["grade"]["relevance_drop_rate"]
                value = event.grade["relevance_drop_rate"]
                if not isclose(value, ratio["rate"], rel_tol=1e-9, abs_tol=1e-12):
                    raise ValueError("relevance_drop_rate must match document counts")
            else:
                value = len(event.guard) if metric == "guard" else getattr(event, metric)
            for bound, limit in bounds.items():
                if (bound == "max" and value > limit) or (bound == "min" and value < limit):
                    warning = {"run_id": event.run_id, "domain": event.domain,
                               "estimated": event.estimated, "metric": metric,
                               "value": value, "bound": bound, "limit": limit}
                    if ratio is not None:
                        warning.update(ratio)
                    warnings.append(warning)
    return warnings
