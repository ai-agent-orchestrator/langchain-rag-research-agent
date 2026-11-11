"""Offline synthetic-data paths through real R35 events and the R38 board."""
from collections import Counter
from dataclasses import replace
import json
from pathlib import Path
import random
from tempfile import TemporaryDirectory

import pytest

from rag_research_agent.core.run_events import RunEvent, cost_krw, from_json
from scripts.make_demo_events import (
    DEMO_PRICING, DOMAINS, ROOT, generate_events, main, summarize_events, write_events,
)
from scripts.metrics_board import load_events, render


@pytest.fixture
def output_root():
    base = ROOT / ".runs/events"
    base.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="r40-test-", dir=base) as directory:
        yield Path(directory)


def test_seed_reproduces_serialized_events_without_global_random_changes():
    before = random.getstate()
    first = generate_events(seed=17, per_domain=3)
    assert random.getstate() == before
    assert [e.to_json(dumps=json.dumps) for e in first] == [
        e.to_json(dumps=json.dumps) for e in generate_events(seed=17, per_domain=3)]
    assert first != generate_events(seed=18, per_domain=3)


def test_four_domains_and_unique_synthetic_ids():
    events = generate_events()
    assert Counter(e.domain for e in events) == dict.fromkeys(DOMAINS, 25)
    assert len({e.run_id for e in events}) == 100
    assert all(e.run_id.removeprefix("demo-").isalpha() for e in events)
    assert all(e.dataset == "synthetic-demo-v1" and e.estimated for e in events)
    assert {e.track for e in events} == {"fast", "deep"}


def test_r35_schema_roundtrip_and_node_accounting():
    for event in generate_events(per_domain=8):
        assert from_json(event.to_json(dumps=json.dumps), loads=json.loads) == event
        assert RunEvent.from_json(event.to_json(dumps=json.dumps), loads=json.loads) == event
        assert tuple(node.name for node in event.nodes) == event.path
        assert event.total_ms == sum(node.ms for node in event.nodes)
        assert 0 <= event.ttft_ms <= event.total_ms
        assert event.loops["rewrite"] == event.path.count("rewrite")
        assert event.loops["gap"] == event.path.count("retrieve_gap")
        assert event.loops["verify"] == event.path.count("verify")
        usage = {}
        for model in DEMO_PRICING:
            nodes = [node for node in event.nodes if node.model == model]
            usage[model] = {"in": sum(n.tokens_in for n in nodes),
                            "out": sum(n.tokens_out for n in nodes)}
            assert event.calls["slm" if model == "demo-slm" else "flagship"] == len(nodes)
        assert event.tokens["in"] == sum(n.tokens_in for n in event.nodes)
        assert event.tokens["out"] == sum(n.tokens_out for n in event.nodes)
        assert event.cost_krw == pytest.approx(cost_krw(usage, DEMO_PRICING))
        assert event.grade["relevance_drop_rate"] == pytest.approx(
            1 - event.grade["docs_kept"] / event.grade["docs_in"])
        if event.track == "fast":
            assert sum(event.loops.values()) == 0


@pytest.mark.parametrize("seed,count", [(True, 2), ("seed-a", 2), (42, 0), (42, -1), (42, True), (42, 1.5)])
def test_invalid_generator_arguments(seed, count):
    with pytest.raises(ValueError):
        generate_events(seed, count)


def test_summary_counts_intervals_and_domain_means():
    original = generate_events(per_domain=1)[0]
    fast = replace(original, run_id="run-a", track="fast", cost_krw=1,
                   loops={"rewrite": 0, "gap": 0, "verify": 0})
    deep = replace(original, run_id="run-b", track="deep", cost_krw=3,
                   loops={"rewrite": 2, "gap": 1, "verify": 1})
    summary = summarize_events(iter((fast, deep)))["estimated"]
    assert summary["n"] == 2
    for track in ("fast", "deep"):
        rate = summary["tracks"][track]
        assert (rate["count"], rate["n"], rate["ratio"]) == (1, 2, .5)
        assert rate["wilson95"] == pytest.approx([.09453121, .90546879], abs=1e-8)
    domain = summary["domains"]["research"]
    assert domain["mean_cost_krw"] == 2
    assert domain["mean_loops"] == {"rewrite": 1, "gap": .5, "verify": .5}
    assert domain["mean_total_loops"] == 2
    assert domain["tracks"] == summary["tracks"]
    assert summary["domains"]["medical"]["mean_cost_krw"] is None


def test_summary_empty_and_estimation_cohorts_are_separate():
    empty = summarize_events([])["estimated"]
    assert empty["n"] == 0 and empty["mean_total_loops"] is None
    assert empty["tracks"]["fast"] == {"count": 0, "n": 0, "ratio": None, "wilson95": None}
    original = generate_events(per_domain=1)[0]
    measured = replace(original, run_id="run-measured", estimated=False, nodes=(), cost_krw=9)
    summary = summarize_events([original, measured])
    assert summary["estimated"]["n"] == summary["non_estimated"]["n"] == 1
    assert summary["estimated"]["mean_cost_krw"] == original.cost_krw
    assert summary["non_estimated"]["mean_cost_krw"] == 9
    rate = summary["non_estimated"]["tracks"]["deep" if measured.track == "fast" else "fast"]
    assert rate["ratio"] == 0 and rate["wilson95"][1] > 0


def test_jsonl_bytes_reproduce_and_r38_loads_four_domains(output_root):
    events = generate_events(seed=7, per_domain=2)
    path = write_events(events, output_root / "batch-a")
    first = path.read_bytes()
    summary_path = path.with_name("summary.json")
    summary_bytes = summary_path.read_bytes()
    write_events(generate_events(seed=7, per_domain=2), path.parent)
    assert path.read_bytes() == first and summary_path.read_bytes() == summary_bytes
    assert json.loads(summary_bytes) == summarize_events(events)
    assert load_events(output_root) == events
    html = render(load_events(output_root))
    assert html.count('data-panel="trace"') == 4
    assert html.count('data-panel="cost"') == 4
    assert "estimated=true" in html and "Wilson 95%" in html
    for domain in DOMAINS:
        assert domain in html


def test_cli_writes_requested_batch_and_rejects_invalid_paths(output_root):
    batch = output_root / "cli-batch"
    main(["--seed", "5", "--per-domain", "1", "--output", str(batch)])
    assert len(load_events(output_root)) == 4
    assert (batch / "summary.json").is_file()
    with pytest.raises(ValueError, match="inside .runs/events"):
        write_events([], ROOT / ".runs" / "r40-outside-events")
    with pytest.raises(ValueError, match="inside .runs/events"):
        write_events([], ROOT / ".runs/events")
    with pytest.raises(SystemExit):
        main(["--per-domain", "0", "--output", str(batch)])
    with pytest.raises(SystemExit):
        main(["--output", str(ROOT / "outside-runs")])
