"""Golden-rule files: load, validate and version. The rules are data, not code (docs/GOLDEN_RULES.ko.md)."""
from __future__ import annotations

MATURITY = "incubating"

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

WEIGHT_KEYS = ("golden_phrase", "concreteness", "causal_reversal", "ontology_priority", "rarity", "cliche_penalty")


@dataclass(frozen=True)
class CausalType:
    id: int
    group: str
    name: str
    cues: tuple[str, ...]
    always_protect: bool = False


@dataclass(frozen=True)
class GoldenRules:
    name: str
    label: str
    rule_version: str                 # hash of the file bytes: every edit is a new version
    weights: dict[str, float]
    number_patterns: tuple[re.Pattern, ...]
    causal_types: tuple[CausalType, ...]
    pillar_cues: dict[str, tuple[str, ...]]
    packs: dict[str, tuple[str, ...]]
    cliche_phrases: tuple[str, ...]


class RulesError(ValueError):
    pass


def parse_rules(raw: bytes) -> GoldenRules:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RulesError(f"rules file is not valid UTF-8 JSON: {exc}") from exc
    weights = data.get("weights", {})
    missing = [k for k in WEIGHT_KEYS if k not in weights]
    if missing:
        raise RulesError(f"weights missing: {missing}")
    if any(not isinstance(weights[k], (int, float)) or weights[k] < 0 for k in WEIGHT_KEYS):
        raise RulesError("weights must be non-negative numbers (cliche_penalty is subtracted)")
    ids = [t["id"] for t in data.get("causal_types", [])]
    if len(ids) != len(set(ids)):
        raise RulesError("duplicate causal type id")
    try:
        patterns = tuple(re.compile(p) for p in data.get("number_patterns", []))
    except re.error as exc:
        raise RulesError(f"bad number pattern: {exc}") from exc
    return GoldenRules(
        name=data.get("name", "unnamed"),
        label=data.get("label", ""),
        rule_version=hashlib.sha256(raw).hexdigest()[:12],
        weights={k: float(weights[k]) for k in WEIGHT_KEYS},
        number_patterns=patterns,
        causal_types=tuple(CausalType(t["id"], t.get("group", ""), t["name"], tuple(t.get("cues", [])),
                                      bool(t.get("always_protect", False))) for t in data.get("causal_types", [])),
        pillar_cues={k: tuple(v) for k, v in data.get("pillar_cues", {}).items()},
        packs={k: tuple(v) for k, v in data.get("packs", {}).items()},
        cliche_phrases=tuple(data.get("cliche_phrases", [])),
    )


def load_rules(path: str | Path) -> GoldenRules:
    return parse_rules(Path(path).read_bytes())
