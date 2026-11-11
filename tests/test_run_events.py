"""Offline contract tests using the real immutable event classes and JSON codec."""
import json
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

import pytest

from rag_research_agent.core.run_events import (
    NodeEvent, RunEvent, cost_krw, from_json, to_json,
)


def sample():
    return {
        "run_id": "run-a1", "domain": "research", "track": "deep",
        "config": "graph_full", "dataset": "cases.ko.v2", "sha": "abc1234",
        "path": ["retrieve", "generate"], "end_type": "END",
        "loops": {"rewrite": 1, "gap": 0, "verify": 0},
        "calls": {"slm": 1, "flagship": 1}, "tokens": {"in": 120, "out": 20},
        "cost_krw": 0.016, "ttft_ms": 10, "total_ms": 30,
        "grade": {"docs_in": 4, "docs_kept": 3, "relevance_drop_rate": 0.25},
        "guard": [{"gate": "grounded", "code": "GAP:metric-a", "reason": "누락", "span": ""}],
        "nodes": [
            {"name": "retrieve", "ms": 10, "tokens_in": 0, "tokens_out": 0,
             "model": None, "estimated": True},
            {"name": "generate", "ms": 20, "tokens_in": 120, "tokens_out": 20,
             "model": "fake-slm", "estimated": False},
        ],
        "estimated": True,
    }


@pytest.mark.parametrize("track", ["fast", "deep"])
@pytest.mark.parametrize("end_type", ["END", "give_up", "cutoff"])
def test_run_round_trip(track, end_type):
    payload = sample()
    payload.update(track=track, end_type=end_type)
    event = RunEvent(**payload)
    encoded = to_json(event, dumps=json.dumps)
    assert json.loads(encoded) == payload
    assert from_json(encoded, loads=json.loads) == event
    assert RunEvent.from_json(event.to_json(dumps=json.dumps), loads=json.loads) == event
    assert event.guard[0]["code"] == "GAP:metric-a"


def test_node_round_trip_and_rule_estimation():
    node = NodeEvent("retrieve", 12, 3, 0, None, False)
    assert node.estimated is True
    assert from_json(to_json(node, dumps=json.dumps), loads=json.loads, event_type=NodeEvent) == node
    payload = sample()
    payload["estimated"] = False
    payload["nodes"][0]["estimated"] = False
    assert RunEvent(**payload).estimated is True
    payload["nodes"] = payload["nodes"][1:]
    assert RunEvent(**payload).estimated is False


@pytest.mark.parametrize("field", [field.name for field in fields(RunEvent)])
def test_missing_run_fields_rejected(field):
    payload = sample()
    del payload[field]
    with pytest.raises((TypeError, ValueError)):
        RunEvent.from_json(json.dumps(payload), loads=json.loads)


@pytest.mark.parametrize("section", ["loops", "calls", "tokens", "grade", "guard", "nodes"])
def test_every_nested_field_is_required(section):
    original = sample()[section]
    original = original[0] if isinstance(original, list) else original
    for key in original:
        payload = sample()
        target = payload[section]
        target = target[0] if isinstance(target, list) else target
        del target[key]
        with pytest.raises((TypeError, ValueError)):
            from_json(json.dumps(payload), loads=json.loads)


@pytest.mark.parametrize("field", [field.name for field in fields(NodeEvent)])
def test_missing_standalone_node_fields_rejected(field):
    payload = sample()["nodes"][0]
    del payload[field]
    with pytest.raises((TypeError, ValueError)):
        NodeEvent.from_json(json.dumps(payload), loads=json.loads)


def test_deep_immutability_and_defensive_copy():
    payload = sample()
    event = RunEvent(**payload)
    with pytest.raises(FrozenInstanceError):
        event.track = "fast"
    with pytest.raises(FrozenInstanceError):
        event.nodes[0].ms = 50
    for mapping, key in ((event.loops, "rewrite"), (event.calls, "slm"),
                         (event.tokens, "in"), (event.grade, "docs_in"),
                         (event.guard[0], "reason")):
        with pytest.raises(TypeError):
            mapping[key] = 99
    payload["path"].append("rewrite")
    payload["loops"]["rewrite"] = 99
    payload["guard"][0]["reason"] = "changed"
    payload["nodes"][0]["ms"] = 99
    assert json.loads(event.to_json(dumps=json.dumps)) == sample()
    assert isinstance(event.path, tuple) and isinstance(event.nodes, tuple)


@pytest.mark.parametrize("key,value", [
    ("track", "other"), ("end_type", "other"), ("estimated", 1),
    ("cost_krw", -1), ("total_ms", float("nan")), ("ttft_ms", float("inf")),
    ("run_id", 1), ("path", "retrieve"), ("nodes", {}), ("guard", {}),
])
def test_invalid_run_values(key, value):
    payload = sample()
    payload[key] = value
    with pytest.raises(ValueError):
        RunEvent(**payload)


@pytest.mark.parametrize("section,key,value", [
    ("tokens", "in", -1), ("tokens", "out", True), ("calls", "slm", 1.5),
    ("grade", "docs_kept", 5), ("grade", "relevance_drop_rate", 1.5),
    ("nodes", "tokens_in", -1), ("nodes", "estimated", "true"),
    ("nodes", "model", 5), ("guard", "reason", None),
])
def test_invalid_nested_values(section, key, value):
    payload = sample()
    target = payload[section]
    target = target[0] if isinstance(target, list) else target
    target[key] = value
    with pytest.raises(ValueError):
        RunEvent(**payload)


def test_unknown_fields_and_non_objects_rejected():
    for payload in ([], None, {**sample(), "unknown": 1}):
        with pytest.raises(ValueError):
            from_json(json.dumps(payload), loads=json.loads)
    payload = sample()
    payload["nodes"][0]["unknown"] = 1
    with pytest.raises(ValueError):
        RunEvent(**payload)
    with pytest.raises(ValueError):
        from_json("{", loads=json.loads)


def test_cost_uses_real_pricing_file_and_separate_directions():
    pricing = json.loads((Path(__file__).resolve().parents[1] / "evals/pricing.json").read_text(encoding="utf-8"))
    tokens = {"fake-slm": {"in": 120, "out": 20},
              "fake-flagship": {"in": 100, "out": 10}}
    assert cost_krw(tokens, pricing) == pytest.approx(0.136)
    assert cost_krw({"fake-slm": {"in": 0, "out": 100}}, pricing) == pytest.approx(0.02)
    assert cost_krw({}, pricing) == 0
    assert cost_krw({"fake-slm": {"in": 0, "out": 0}}, pricing) == 0
    with pytest.raises(KeyError):
        cost_krw({"unknown": {"in": 1, "out": 0}}, pricing)


@pytest.mark.parametrize("usage,rates", [
    ({"in": -1, "out": 0}, {"in": 1, "out": 2}),
    ({"in": 1.5, "out": 0}, {"in": 1, "out": 2}),
    ({"in": True, "out": 0}, {"in": 1, "out": 2}),
    ({"in": 1}, {"in": 1, "out": 2}),
    ({"in": 1, "out": 0}, {"in": -1, "out": 2}),
    ({"in": 1, "out": 0}, {"in": float("nan"), "out": 2}),
    ({"in": 1, "out": 0}, {"in": float("inf"), "out": 2}),
    ({"in": 1, "out": 0}, {"in": 1}),
])
def test_invalid_cost_inputs(usage, rates):
    with pytest.raises(ValueError):
        cost_krw({"fake-slm": usage}, {"fake-slm": rates})
