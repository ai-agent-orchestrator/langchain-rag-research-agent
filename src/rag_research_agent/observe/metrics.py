"""Strict numeric local events; no prompt, document, identity or exception text.

One recorder owns its in-memory events. An optional JSONL sink appends those
events; existing lines are only loaded explicitly with ``from_jsonl``.
"""
from __future__ import annotations

MATURITY = "incubating"

from collections import Counter
import json
import math
from pathlib import Path

from rag_research_agent.core.contracts import RetrievalStatus, RetrievalUnavailable
from rag_research_agent.core.types import Status

STAGES = frozenset({"retrieve", "grade", "generate", "answer"})
STATUSES = frozenset({str(s) for s in RetrievalStatus} | {str(s) for s in Status} | {
    "ANSWERED", "UNAVAILABLE", "INFERENCE_TIMEOUT", "GENERATION_CAPACITY_EXCEEDED",
    RetrievalUnavailable.code,
})
ALLOWED_KEYS = frozenset({
    "stage", "latency_ms", "status", "input_length", "output_length", "slots_occupied",
})


def _validate(event):
    # Keep error messages constant: even rejected values/keys may contain PII.
    if not isinstance(event, dict) or set(event) != ALLOWED_KEYS:
        raise ValueError("event must contain exactly the allowed metric keys")
    if not isinstance(event["stage"], str) or event["stage"] not in STAGES:
        raise ValueError("invalid metric stage")
    if not isinstance(event["status"], str) or event["status"] not in STATUSES:
        raise ValueError("invalid metric status")
    latency = event["latency_ms"]
    if type(latency) not in (int, float):
        raise ValueError("latency_ms must be finite and nonnegative")
    try:
        valid = math.isfinite(latency) and latency >= 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError("latency_ms must be finite and nonnegative")
    for key in ("input_length", "output_length", "slots_occupied"):
        if type(event[key]) is not int or event[key] < 0:
            raise ValueError("lengths and occupancy must be nonnegative integers")
    return dict(event)


def _runs_path(path):
    root = Path(".runs").resolve()
    target = Path(path).resolve()
    if not target.is_relative_to(root) or target == root:
        raise ValueError("metrics files must be inside .runs")
    return target


def _percentile(values, quantile):
    """Linear interpolation at (n - 1) * quantile; a singleton returns itself."""
    values = sorted(values)
    index = (len(values) - 1) * quantile
    lower, upper = math.floor(index), math.ceil(index)
    weight = index - lower
    return values[lower] * (1 - weight) + values[upper] * weight


def summarize(events):
    """Event-level timeout rate (INFERENCE_TIMEOUT), with n and Wilson 95% CI.

    Empty stages have count 0 and null percentiles. An empty sample has a null
    rate/interval, rather than claiming no timeouts. Counts are events, not requests.
    """
    rows = [_validate(event) for event in events]
    stages = {}
    for stage in sorted(STAGES):
        latencies = [row["latency_ms"] for row in rows if row["stage"] == stage]
        stages[stage] = {
            "count": len(latencies),
            "p50_ms": _percentile(latencies, .5) if latencies else None,
            "p95_ms": _percentile(latencies, .95) if latencies else None,
        }
    total = len(rows)
    count = sum(row["status"] == "INFERENCE_TIMEOUT" for row in rows)
    rate, interval = None, None
    if total:
        rate = count / total
        z = 1.959963984540054
        denominator = 1 + z * z / total
        center = (rate + z * z / (2 * total)) / denominator
        half = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denominator
        interval = [max(0.0, center - half), min(1.0, center + half)]
    return {
        "count": total,
        "stages": stages,
        "statuses": dict(sorted(Counter(row["status"] for row in rows).items())),
        "timeout": {"count": count, "total": total, "rate": rate, "wilson95": interval},
    }


class LocalMetrics:
    """In-memory recorder with an optional append-only .runs JSONL sink.

    Callers supply character counts and worker occupancy, never source strings.
    Intended for one owning thread; concurrent writers and file rotation are not
    implemented. A failed disk append does not add an event to memory.
    """

    def __init__(self, path=None):
        self._path = _runs_path(path) if path is not None else None
        self._events = []

    @property
    def events(self):
        return tuple(dict(event) for event in self._events)

    def record(self, **event):
        payload = _validate(event)
        if self._path is not None:
            path = _runs_path(self._path)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, allow_nan=False) + "\n")
        self._events.append(payload)
        return dict(payload)

    def summary(self):
        return summarize(self._events)

    @classmethod
    def from_jsonl(cls, path):
        """Load and validate every line into memory; never re-append loaded lines."""
        recorder = cls()
        with _runs_path(path).open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    payload = json.loads(line)
                except ValueError:
                    raise ValueError("invalid metric JSONL") from None
                recorder._events.append(_validate(payload))
        return recorder
