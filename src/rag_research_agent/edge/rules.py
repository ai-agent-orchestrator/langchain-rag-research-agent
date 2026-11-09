"""Golden-rule files: load, validate and version. The rules are data, not code (docs/GOLDEN_RULES.ko.md)."""
from __future__ import annotations

MATURITY = "incubating"

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

WEIGHT_KEYS = ("golden_phrase", "concreteness", "causal_reversal", "ontology_priority", "rarity", "cliche_penalty")
OPTIONAL_WEIGHT_KEYS = {"boost": 0.0}


@dataclass(frozen=True)
class CausalType:
    id: int
    group: str
    name: str
    cues: tuple[str, ...]
    always_protect: bool = False


@dataclass(frozen=True)
class RuleItem:
    id: str
    pillar: str
    name: str
    cues: tuple[str, ...] = ()
    patterns: tuple[re.Pattern, ...] = ()
    always_protect: bool = False
    weight: float = 1.0               # used by weight (boost) rules

    def matches(self, text: str) -> bool:
        return any(c and c in text for c in self.cues) or any(p.search(text) for p in self.patterns)


@dataclass(frozen=True)
class GoldenRules:
    name: str
    label: str
    rule_version: str                 # hash of the file bytes: every edit is a new version
    weights: dict[str, float]
    number_patterns: tuple[re.Pattern, ...]
    causal_types: tuple[CausalType, ...]
    pillar_rules: tuple[RuleItem, ...]      # correlation / trend / numbers / attribution
    packs: dict[str, tuple[RuleItem, ...]]  # domain packs, switched on per run
    cliche_rules: tuple[RuleItem, ...]
    penalize_cliche_only_without_content: bool = True
    weight_rules: tuple[RuleItem, ...] = ()


def _item(raw: dict, pillar: str | None = None) -> RuleItem:
    try:
        patterns = tuple(re.compile(p) for p in raw.get("patterns", []))
    except re.error as exc:
        raise RulesError(f"bad pattern in rule {raw.get('id')}: {exc}") from exc
    if not raw.get("cues") and not patterns:
        raise RulesError(f"rule {raw.get('id')} has neither cues nor patterns")
    weight = raw.get("weight", 1.0)
    if not isinstance(weight, (int, float)) or weight <= 0:
        raise RulesError(f"rule {raw.get('id')} weight must be positive")
    return RuleItem(str(raw["id"]), pillar or raw.get("pillar", ""), raw.get("name", ""),
                    tuple(raw.get("cues", [])), patterns, bool(raw.get("always_protect", False)), float(weight))


def _legacy_items(prefix: str, pillar: str, cues) -> tuple[RuleItem, ...]:
    return tuple(RuleItem(f"{prefix}{i}", pillar, c, (c,)) for i, c in enumerate(cues, 1))


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
    pillar = tuple(_item(r) for r in data.get("pillar_rules", []))
    for name, cues in data.get("pillar_cues", {}).items():          # older format
        pillar += _legacy_items(name[:1].upper(), name, cues)
    cliche = tuple(_item(r, "cliche") for r in data.get("cliche_rules", []))
    cliche += _legacy_items("X", "cliche", data.get("cliche_phrases", []))
    packs = {}
    for name, pack in data.get("packs", {}).items():
        if isinstance(pack, dict):
            packs[name] = tuple(_item(r, name) for r in pack.get("rules", []))
        else:                                                         # older format: list of cues
            packs[name] = _legacy_items(name[:1].upper(), name, pack)
    weight_rules = tuple(_item(r, "weight") for r in data.get("weight_rules", []))
    all_ids = [i.id for i in pillar + cliche + weight_rules] + [i.id for v in packs.values() for i in v]
    if len(all_ids) != len(set(all_ids)):
        raise RulesError("duplicate rule id")
    return GoldenRules(
        name=data.get("name", "unnamed"),
        label=data.get("label", ""),
        rule_version=hashlib.sha256(raw).hexdigest()[:12],
        weights={**{k: float(weights[k]) for k in WEIGHT_KEYS},
                 **{k: float(weights.get(k, v)) for k, v in OPTIONAL_WEIGHT_KEYS.items()}},
        number_patterns=patterns,
        causal_types=tuple(CausalType(t["id"], t.get("group", ""), t["name"], tuple(t.get("cues", [])),
                                      bool(t.get("always_protect", False))) for t in data.get("causal_types", [])),
        pillar_rules=pillar,
        packs=packs,
        cliche_rules=cliche,
        penalize_cliche_only_without_content=bool(
            data.get("cliche_policy", {}).get("penalize_only_without_content", True)),
        weight_rules=weight_rules,
    )


def load_rules(path: str | Path) -> GoldenRules:
    return parse_rules(Path(path).read_bytes())
