"""Immutable metrics events; JSON codecs are injected to keep core independent.

Use ``event.to_json(dumps=json.dumps)`` and
``RunEvent.from_json(text, loads=json.loads)`` at the application boundary.
Prices are KRW per million tokens, keyed by model, with ``in``/``out`` rates.
No prices, token counts, timing or guard text are collected implicitly.
"""
from __future__ import annotations

from dataclasses import dataclass, fields
from typing import Callable, Literal, Mapping

MATURITY = "incubating"


@dataclass(frozen=True)
class _FrozenMap(Mapping):
    entries: tuple

    def __getitem__(self, key):
        for name, value in self.entries:
            if name == key:
                return value
        raise KeyError(key)

    def __iter__(self):
        return (name for name, _ in self.entries)

    def __len__(self):
        return len(self.entries)


def _object(value, keys):
    if not isinstance(value, Mapping) or set(value) != set(keys):
        raise ValueError("object fields do not match schema")
    return value


def _number(value, name, *, integer=False):
    if type(value) not in ((int,) if integer else (int, float)):
        raise ValueError(f"{name} must be a nonnegative number")
    if not 0 <= value < float("inf"):
        raise ValueError(f"{name} must be finite and nonnegative")
    return value


def _text(value):
    if type(value) is not str:
        raise ValueError("expected string")
    return value


def _sequence(value):
    if not isinstance(value, (list, tuple)):
        raise ValueError("expected array")
    return value


def _counts(value, keys):
    value = _object(value, keys)
    return _FrozenMap(tuple((key, _number(value[key], key, integer=True)) for key in keys))


def _plain(value):
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    if isinstance(value, (RunEvent, NodeEvent)):
        return {field.name: _plain(getattr(value, field.name)) for field in fields(value)}
    return value


class _JsonEvent:
    def to_json(self, *, dumps: Callable[..., str]) -> str:
        """Serialize using an explicit JSON encoder (e.g. stdlib json.dumps)."""
        return dumps(_plain(self), ensure_ascii=False, allow_nan=False)

    @classmethod
    def from_json(cls, payload: str, *, loads: Callable[[str], object]):
        """Decode and validate all fields, including nested required fields."""
        value = _object(loads(payload), (field.name for field in fields(cls)))
        return cls(**value)


@dataclass(frozen=True)
class NodeEvent(_JsonEvent):
    name: str
    ms: float
    tokens_in: int
    tokens_out: int
    model: str | None
    estimated: bool

    def __post_init__(self):
        _text(self.name)
        _number(self.ms, "ms")
        _number(self.tokens_in, "tokens_in", integer=True)
        _number(self.tokens_out, "tokens_out", integer=True)
        if self.model is not None:
            _text(self.model)
        if type(self.estimated) is not bool:
            raise ValueError("estimated must be boolean")
        if self.model is None:
            object.__setattr__(self, "estimated", True)


@dataclass(frozen=True)
class RunEvent(_JsonEvent):
    run_id: str
    domain: str
    track: Literal["fast", "deep"]
    config: str
    dataset: str
    sha: str
    path: tuple[str, ...]
    end_type: Literal["END", "give_up", "cutoff"]
    loops: Mapping[str, int]
    calls: Mapping[str, int]
    tokens: Mapping[str, int]
    cost_krw: float
    ttft_ms: float
    total_ms: float
    grade: Mapping[str, int | float]
    guard: tuple[Mapping[str, str], ...]
    nodes: tuple[NodeEvent, ...]
    estimated: bool

    def __post_init__(self):
        for name in ("run_id", "domain", "config", "dataset", "sha"):
            _text(getattr(self, name))
        if self.track not in ("fast", "deep") or self.end_type not in ("END", "give_up", "cutoff"):
            raise ValueError("invalid track or end_type")
        object.__setattr__(self, "path", tuple(_text(name) for name in _sequence(self.path)))
        for name, keys in (("loops", ("rewrite", "gap", "verify")),
                           ("calls", ("slm", "flagship")), ("tokens", ("in", "out"))):
            object.__setattr__(self, name, _counts(getattr(self, name), keys))
        for name in ("cost_krw", "ttft_ms", "total_ms"):
            _number(getattr(self, name), name)
        grade = _object(self.grade, ("docs_in", "docs_kept", "relevance_drop_rate"))
        for name in ("docs_in", "docs_kept"):
            _number(grade[name], name, integer=True)
        rate = _number(grade["relevance_drop_rate"], "relevance_drop_rate")
        if grade["docs_kept"] > grade["docs_in"] or rate > 1:
            raise ValueError("invalid grade bounds")
        object.__setattr__(self, "grade", _FrozenMap(tuple(grade.items())))
        guards = []
        for item in _sequence(self.guard):
            item = _object(item, ("gate", "code", "reason", "span"))
            guards.append(_FrozenMap(tuple((key, _text(value)) for key, value in item.items())))
        object.__setattr__(self, "guard", tuple(guards))
        nodes = []
        for node in _sequence(self.nodes):
            if not isinstance(node, NodeEvent):
                node = NodeEvent(**_object(node, (field.name for field in fields(NodeEvent))))
            nodes.append(node)
        object.__setattr__(self, "nodes", tuple(nodes))
        if type(self.estimated) is not bool:
            raise ValueError("estimated must be boolean")
        if any(node.estimated for node in nodes):
            object.__setattr__(self, "estimated", True)


def to_json(event: RunEvent | NodeEvent, *, dumps: Callable[..., str]) -> str:
    return event.to_json(dumps=dumps)


def from_json(payload: str, *, loads: Callable[[str], object],
              event_type: type[RunEvent] | type[NodeEvent] = RunEvent) -> RunEvent | NodeEvent:
    return event_type.from_json(payload, loads=loads)


def cost_krw(tokens: Mapping[str, Mapping[str, int]],
             pricing: Mapping[str, Mapping[str, float]]) -> float:
    """Sum model-keyed token usage at KRW/million rates; unknown models fail.

    Example: {"fake-slm": {"in": 100, "out": 20}}. Rule-based shadow
    usage can be priced under an explicitly chosen fake model; it remains
    estimated on the event. This function neither loads files nor calls models.
    """
    if not isinstance(tokens, Mapping) or not isinstance(pricing, Mapping):
        raise ValueError("tokens and pricing must be model-keyed objects")
    total = 0.0
    for model, usage in tokens.items():
        _text(model)
        counts = _counts(usage, ("in", "out"))
        rates = _object(pricing[model], ("in", "out"))
        for direction in ("in", "out"):
            rate = _number(rates[direction], direction)
            total += counts[direction] / 1_000_000 * rate
    return _number(total, "cost_krw")
