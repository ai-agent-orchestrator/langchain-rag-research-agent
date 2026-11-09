"""Observation interfaces (LangSmith stays an adapter, off in serving)."""
from __future__ import annotations

MATURITY = "incubating"

from typing import Any, Protocol


class Tracer(Protocol):
    def record(self, event: str, payload: dict[str, Any]) -> None: ...


class Evaluator(Protocol):
    def evaluate(self, rows: list[dict]) -> dict: ...


class FakeTracer:
    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def record(self, event: str, payload: dict[str, Any]) -> None:
        self.events.append((event, payload))


class FakeEvaluator:
    def evaluate(self, rows: list[dict]) -> dict:
        return {"rows": len(rows)}
