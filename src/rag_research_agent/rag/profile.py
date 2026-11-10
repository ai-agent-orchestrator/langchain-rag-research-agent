"""Filter profiles: one JSON file = one domain filter (ontology classes, diet order, never-remove classes,
knobs, packs, focus, external switch). Anyone can copy profiles/_template.json, customize it and use it:

    from rag_research_agent import Equalizer
    brief, trace = Equalizer.from_profile("profiles/litigation.json").brief(text, budget=400)
"""
from __future__ import annotations

MATURITY = "incubating"

import json
from dataclasses import dataclass, field
from pathlib import Path

from rag_research_agent.core.types import Knobs
from rag_research_agent.edge.rules import GoldenRules, load_rules
from rag_research_agent.knobs.mapper import EqualizerConfig, Preset, load_config
from rag_research_agent.ontology.rule_labeler import RuleLabeler, parse_classes
from rag_research_agent.rag.brief import DEFAULT_CONFIG, DEFAULT_RULES, ROOT, Parts, build_brief

PROFILES_DIR = ROOT / "profiles"


class ProfileError(ValueError):
    pass


@dataclass
class Profile:
    name: str
    label: str
    preset: Preset
    labeler: RuleLabeler
    diet_order: tuple[str, ...]
    never_remove: tuple[str, ...]
    rules_path: Path
    raw: dict = field(repr=False, default_factory=dict)


def load_profile(path: str | Path, base_config: str | Path = DEFAULT_CONFIG) -> Profile:
    path = Path(path)
    if not path.exists() and (PROFILES_DIR / f"{path}.json").exists():
        path = PROFILES_DIR / f"{path}.json"                    # allow load_profile("litigation")
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProfileError(f"cannot read profile {path}: {exc}") from exc
    base = json.loads(Path(base_config).read_text(encoding="utf-8"))
    levels = base.get("levels", {"Low": 0.2, "Mid": 0.5, "High": 0.8})

    def level(v, default):
        v = default if v is None else v
        if isinstance(v, str):
            if v not in levels:
                raise ProfileError(f"unknown knob level {v!r}; use {sorted(levels)} or a number 0..1")
            return float(levels[v])
        return float(v)

    k = d.get("knobs", {})
    onto = d.get("ontology", {})
    classes = parse_classes(onto.get("classes", []))
    names = {c.name for c in classes} | {"Unclassified"}
    for key in ("diet_order", "never_remove"):
        unknown = [x for x in onto.get(key, []) if x not in names]
        if unknown:
            raise ProfileError(f"{key} names classes that are not defined: {unknown}")
    rules = d.get("rules", "default")
    rules_path = DEFAULT_RULES if rules == "default" else (path.parent / rules).resolve()
    preset = Preset(d.get("name", path.stem), Knobs(level(k.get("similarity"), "Mid"), level(k.get("edge_weight"), "High")),
                    bool(d.get("external_allowed", True)), tuple(d.get("packs", ())), d.get("label", path.stem),
                    tuple((kw, float(w)) for kw, w in d.get("focus", {}).items()))
    return Profile(preset.name, preset.label, preset, RuleLabeler(classes),
                   tuple(onto.get("diet_order", ("Unclassified",))), tuple(onto.get("never_remove", ())), rules_path, d)


class Equalizer:
    """The reusable entry point. Holds one profile; swap profiles to switch domains."""

    def __init__(self, profile: Profile, rules: GoldenRules | None = None, base_config: str | Path = DEFAULT_CONFIG):
        self.profile = profile
        base = load_config(base_config)
        self.config = EqualizerConfig(base.mapper, {profile.name: profile.preset}, profile.diet_order, profile.never_remove)
        self.rules = rules or load_rules(profile.rules_path)

    @classmethod
    def from_profile(cls, path_or_name: str | Path) -> "Equalizer":
        return cls(load_profile(path_or_name))

    def parts(self, parts_preset="v0", **overrides) -> Parts:
        if parts_preset not in ("v0", "v1"):
            raise ValueError("parts_preset must be v0 or v1")
        factory = Parts.with_defaults_v1 if parts_preset == "v1" else Parts
        return factory(rules=self.rules, config=self.config, labeler=self.profile.labeler, **overrides)

    def brief(self, text: str, task: str | None = None, budget: int = 600, knobs: Knobs | None = None,
              focus: dict[str, float] | None = None, parts_preset="v0", **part_overrides):
        return build_brief(text, task, knobs, None if knobs else self.profile.name, budget, focus, None,
                           self.parts(parts_preset, **part_overrides))


def list_profiles(directory: str | Path = PROFILES_DIR) -> list[str]:
    return sorted(p.stem for p in Path(directory).glob("*.json") if not p.stem.startswith("_"))
