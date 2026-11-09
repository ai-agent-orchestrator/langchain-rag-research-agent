"""Knob interfaces. M0: protocols and a fake only; calibration values are not decided here."""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass
from typing import Protocol

from rag_research_agent.core.types import Knobs


@dataclass(frozen=True)
class InternalSettings:
    top_k: int
    threshold: float
    extract_only: bool


class KnobMapper(Protocol):
    def map(self, knobs: Knobs) -> InternalSettings: ...


class Preset(Protocol):
    name: str
    knobs: Knobs


class FakeKnobMapper:
    """Placeholder mapping for wiring tests only (not the calibrated formula)."""
    def map(self, knobs: Knobs) -> InternalSettings:
        return InternalSettings(top_k=10, threshold=knobs.similarity, extract_only=knobs.edge_weight >= 0.5)
