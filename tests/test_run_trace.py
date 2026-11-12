"""Offline path tests using the real runner, event classes and local sink."""
from dataclasses import replace
from itertools import count
import json
from pathlib import Path
from uuid import uuid4

import pytest
from langchain_core.outputs import Generation, LLMResult

from rag_research_agent.core.run_events import RunEvent
from rag_research_agent.rag.research_graph import ResearchConfig, ResearchRunner, keyword_search
from rag_research_agent.rag.run_trace import (
    JsonlSink, TraceCollector, TraceResearchRunner, event_from_result,
)


def runner(cfg=ResearchConfig(), cls=ResearchRunner, **kwargs):
    return cls(keyword_search({"doc-a1": "매출은 18% 증가했다."}), cfg, **kwargs)


def result():
    return runner().run("매출을 정리해 주세요.")


def test_adapter_path_tokens_and_loop_counts():
    original = result()
    event = event_from_result(original, "research", {})
    assert event.path == original.path
    assert event.tokens["in"] + event.tokens["out"] == original.shadow_tokens
    assert dict(event.calls) == {"slm": 0, "flagship": 0}
    assert all(n.model is None and n.estimated for n in event.nodes)
    repeated = replace(original,
        path=("write", "verify", "rewrite", "retrieve_gap", "write", "verify"),
        cost=(("write", "model_in", 5), ("write", "model_out", 2),
              ("write", "model_in", 7), ("write", "model_out", 3)))
    adapted = event_from_result(repeated, "research", {})
    assert dict(adapted.loops) == {"rewrite": 1, "gap": 1, "verify": 1}
    assert [(n.tokens_in, n.tokens_out) for n in adapted.nodes if n.name == "write"] == [(5, 2), (7, 3)]


@pytest.mark.parametrize("cfg,expected", [
    (ResearchConfig(), "END"),
    (ResearchConfig(no_con_policy="stop"), "give_up"),
    (ResearchConfig(per_node_token_cap=1), "cutoff"),
])
def test_real_graph_end_types(cfg, expected):
    event = event_from_result(runner(cfg).run("매출을 정리해 주세요."), "research", {})
    assert event.end_type == expected


def test_unresolved_budget_and_interrupt_are_not_success():
    original = result()
    failed = replace(original, verify_codes=("GAP:매출",))
    assert event_from_result(failed, "research", {}).end_type == "give_up"
    assert event_from_result(failed, "research", {"max_shadow_tokens": 1}).end_type == "cutoff"
    assert event_from_result(replace(original, interrupts=("review",)), "research", {}).end_type == "give_up"


def test_jsonl_appends_and_round_trips(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    sink = JsonlSink()
    event = event_from_result(result(), "research", {"run_id": "run-a1"})
    sink(event)
    sink(event)
    lines = Path(".runs/events/research/events.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert all(RunEvent.from_json(line, loads=json.loads) == event for line in lines)


@pytest.mark.parametrize("domain", ["../outside", "legal/other", "", ".."])
def test_sink_rejects_unsafe_domain(tmp_path, monkeypatch, domain):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        JsonlSink()(event_from_result(result(), domain, {}))
    assert not Path(".runs").exists()


def test_sink_rejects_output_outside_runs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        JsonlSink(tmp_path / "outside")


def test_disabled_trace_has_no_clock_sink_or_files(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    original = result()
    traced = runner(cls=TraceResearchRunner).run("매출을 정리해 주세요.")
    assert traced == original
    assert not Path(".runs").exists()


def test_enabled_trace_uses_real_graph_callbacks(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    ticks = count()
    collector = TraceCollector(clock=lambda: next(ticks) / 1000)
    traced_runner = runner(cls=TraceResearchRunner, trace=collector)
    first = traced_runner.run("매출을 정리해 주세요.")
    event = collector.last_event
    assert tuple(n.name for n in event.nodes) == first.path
    assert all(n.ms > 0 for n in event.nodes)
    assert event.total_ms > 0
    assert event.tokens["in"] + event.tokens["out"] == first.shadow_tokens
    traced_runner.run("매출을 정리해 주세요.")
    assert collector.last_event.run_id != event.run_id
    assert len(Path(".runs/events/research/events.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_callback_measured_model_tokens_calls_and_pricing():
    events = []
    ticks = count()
    collector = TraceCollector(clock=lambda: next(ticks) / 1000, sink=events.append,
        config={"model_roles": {"local-slm": "slm"},
                "pricing": {"local-slm": {"in": 100, "out": 200}}})
    collector.begin()
    node_id, model_id = uuid4(), uuid4()
    collector.on_chain_start(None, {}, run_id=node_id, name="write",
        metadata={"langgraph_node": "write"}, tags=["graph:step:1"])
    collector.on_llm_start(None, [], run_id=model_id, parent_run_id=node_id,
        invocation_params={"model_name": "local-slm"})
    collector.on_llm_end(LLMResult(generations=[[Generation(text="")]],
        llm_output={"token_usage": {"prompt_tokens": 20, "completion_tokens": 5}}), run_id=model_id)
    collector.on_chain_end({}, run_id=node_id)
    event = collector.finish(replace(result(), path=("write",)), max_shadow_tokens=12000)
    assert event.nodes[0].ms == pytest.approx(1)
    assert event.total_ms == pytest.approx(3)
    assert dict(event.tokens) == {"in": 20, "out": 5}
    assert dict(event.calls) == {"slm": 1, "flagship": 0}
    assert event.cost_krw == pytest.approx(.003)
    assert events == [event]


def test_nested_callbacks_do_not_duplicate_nodes_or_copy_text():
    collector = TraceCollector(sink=lambda event: None)
    collector.begin()
    outer, inner = uuid4(), uuid4()
    metadata = {"langgraph_node": "write"}
    collector.on_chain_start(None, {}, run_id=outer, name="write", metadata=metadata, tags=["graph:step:1"])
    collector.on_chain_start(None, {}, run_id=inner, name="nested", metadata=metadata, parent_run_id=outer)
    collector.on_chain_end({"report": "DO_NOT_COPY"}, run_id=inner)
    collector.on_chain_end({"report": "DO_NOT_COPY"}, run_id=outer)
    event = collector.finish(replace(result(), path=("write",)), max_shadow_tokens=12000)
    assert len(event.nodes) == 1
    assert "DO_NOT_COPY" not in event.to_json(dumps=json.dumps)


def test_parallel_invocations_and_first_token_use_injected_clock():
    ticks = count()
    collector = TraceCollector(clock=lambda: next(ticks) / 1000, sink=lambda event: None)
    collector.begin()
    first, second = uuid4(), uuid4()
    for run_id, name in ((first, "retrieve_base"), (second, "retrieve_pro")):
        collector.on_chain_start(None, {}, run_id=run_id, name=name,
            metadata={"langgraph_node": name}, tags=["graph:step:1"])
    collector.on_llm_new_token("DO_NOT_COPY")
    collector.on_chain_end({}, run_id=second)
    collector.on_chain_end({}, run_id=first)
    event = collector.finish(replace(result(), path=("retrieve_base", "retrieve_pro")), max_shadow_tokens=12000)
    assert event.path == ("retrieve_base", "retrieve_pro")
    assert [(n.name, round(n.ms)) for n in event.nodes] == [("retrieve_pro", 2), ("retrieve_base", 4)]
    assert event.ttft_ms == pytest.approx(3)
    assert event.total_ms == pytest.approx(6)
    assert "DO_NOT_COPY" not in event.to_json(dumps=json.dumps)


@pytest.mark.parametrize("role", ["slm", "flagship"])
@pytest.mark.parametrize("partial_usage", [False, True])
def test_failed_model_attempt_and_retry_are_both_counted(role, partial_usage):
    from langchain_core.callbacks import CallbackManager

    ticks = count()
    collector = TraceCollector(clock=lambda: next(ticks) / 1000, sink=lambda event: None,
        config={"model_roles": {"local-model": role}})
    collector.begin()
    node_id = uuid4()
    collector.on_chain_start(None, {}, run_id=node_id, name="write",
        metadata={"langgraph_node": "write"}, tags=["graph:step:1"])
    callbacks = CallbackManager([collector], parent_run_id=node_id)
    failed = callbacks.on_llm_start({}, ["DO_NOT_COPY"],
        invocation_params={"model_name": "local-model"})[0]
    kwargs = {}
    if partial_usage:
        kwargs["response"] = LLMResult(generations=[[Generation(text="DO_NOT_COPY")]],
            llm_output={"token_usage": {"prompt_tokens": 7, "completion_tokens": 2}})
    failed.on_llm_error(RuntimeError("DO_NOT_COPY"), **kwargs)
    retried = callbacks.on_llm_start({}, ["DO_NOT_COPY"],
        invocation_params={"model_name": "local-model"})[0]
    retried.on_llm_end(LLMResult(generations=[[Generation(text="DO_NOT_COPY")]],
        llm_output={"token_usage": {"prompt_tokens": 11, "completion_tokens": 3}}))
    collector.on_chain_end({"cost": [("write", "model_in", 100)]}, run_id=node_id)
    event = collector.finish(replace(result(), path=("write",)), max_shadow_tokens=12000)
    assert dict(event.calls) == {"slm": 2 if role == "slm" else 0,
                                 "flagship": 2 if role == "flagship" else 0}
    assert dict(event.tokens) == {"in": 18 if partial_usage else 11,
                                  "out": 5 if partial_usage else 3}
    assert [n.estimated for n in event.nodes] == [not partial_usage, False]
    assert [n.ms for n in event.nodes] == pytest.approx([1, 0])
    assert "DO_NOT_COPY" not in event.to_json(dumps=json.dumps)
