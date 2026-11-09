"""Knob 1 (spear, similarity) and knob 2 (shield, edge weight) -> internal settings. DESIGN 5.

v0: linear mapping with UNCALIBRATED tau values from data/equalizer/presets_v0.json. Swap this module
for a calibrated mapper (per embedding model) without touching the rest of the pipeline.
"""
from __future__ import annotations

MATURITY = "incubating"

import json
from dataclasses import dataclass, field
from pathlib import Path

from rag_research_agent.core.types import Knobs


@dataclass(frozen=True)
class Settings:
    threshold: float          # tau(s): minimum relevance for ordinary candidates
    top_k: int                # k(s): width of the ordinary candidate list
    edge_weight: float        # w
    extract_only: bool        # w >= extract_only_from: original sentences only, protected path active
    protected_path: bool


@dataclass(frozen=True)
class LinearKnobMapper:
    tau_low: float = 0.0
    tau_high: float = 0.6
    k_low: int = 30
    k_high: int = 8
    extract_only_from: float = 0.5

    def map(self, knobs: Knobs) -> Settings:
        s, w = knobs.similarity, knobs.edge_weight
        extract = w >= self.extract_only_from
        return Settings(threshold=round(self.tau_low + s * (self.tau_high - self.tau_low), 4),
                        top_k=max(1, round(self.k_low + s * (self.k_high - self.k_low))),
                        edge_weight=w, extract_only=extract, protected_path=extract)


def blend(relevance: float, edge: float, w: float) -> float:
    """final = (1 - w) * relevance + w * edge (DESIGN 5-2)."""
    return round((1.0 - w) * relevance + w * edge, 4)


@dataclass(frozen=True)
class Preset:
    name: str
    knobs: Knobs
    external_allowed: bool = True
    packs: tuple[str, ...] = ()
    label: str = ""
    focus: tuple[tuple[str, float], ...] = ()   # default focus keywords (name, weight)


@dataclass(frozen=True)
class EqualizerConfig:
    mapper: LinearKnobMapper
    presets: dict[str, Preset]
    class_order: tuple[str, ...] = ()
    never_remove: tuple[str, ...] = ()
    source: dict = field(default_factory=dict, compare=False, repr=False)


def load_config(path: str | Path) -> EqualizerConfig:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    levels = data.get("levels", {"Low": 0.2, "Mid": 0.5, "High": 0.8})

    def level(v):
        return float(levels[v]) if isinstance(v, str) else float(v)

    presets = {}
    for name, p in data.get("presets", {}).items():
        pre = Preset(name, Knobs(level(p["similarity"]), level(p["edge_weight"])), bool(p.get("external_allowed", True)),
                     tuple(p.get("packs", ())), p.get("label", name), tuple((k, float(v)) for k, v in p.get("focus", {}).items()))
        for key in [name, *p.get("aliases", [])]:
            presets[key] = pre
    diet = data.get("diet", {})
    return EqualizerConfig(LinearKnobMapper(**data.get("mapper", {})), presets,
                           tuple(diet.get("class_order", ())), tuple(diet.get("never_remove", ())), data)
