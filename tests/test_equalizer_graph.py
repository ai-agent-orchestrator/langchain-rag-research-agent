import asyncio
from copy import deepcopy
import json
from pathlib import Path
import socket

import pytest

from rag_research_agent.core.types import Knobs, Status
from rag_research_agent.observe.local_log import ALLOWED, append_trace
from rag_research_agent.rag.brief import Parts, build_brief
from rag_research_agent.rag.equalizer_graph import build_graph
from rag_research_agent.rag.profile import Equalizer

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("profile", ["research", "litigation", "macro"])
@pytest.mark.parametrize("name", ["legal_synthetic_v1", "macro_synthetic_v1"])
def test_graph_and_python_share_results(profile, name):
    text = json.loads((ROOT / f"data/golden_sets/{name}.json").read_text(encoding="utf-8"))["draft"]
    eq = Equalizer.from_profile(profile)
    expected, trace = eq.brief(text)
    result = build_graph(profile=profile, log_path=None).invoke({"raw_draft": text})
    assert result["brief"] == expected
    assert result["rows"] == trace.rows and result["settings"] == trace.settings
    assert result["final_prompt_input"] == expected.final_prompt_input
    assert result["generation_calls"] == 0


@pytest.mark.parametrize("text,task,knobs,status", [
    ("[BLOCK] 합성 입력", None, None, Status.BLOCKED),
    ("합성 문서다.", "없는키워드", Knobs(1, 0), Status.REQUEST_MORE),
])
def test_early_termination_never_diets_or_composes(text, task, knobs, status):
    result = build_graph(log_path=None).invoke({"raw_draft": text, "task": task, "knobs": knobs})
    assert result["status"] == status
    assert "diet" not in result["node_calls"] and "compose_and_check" not in result["node_calls"]


def test_overflow_retains_legacy_protected_brief():
    text = "다만 위험은 확인되지 않았다. 핵심은 비용이다."
    eq = Equalizer.from_profile("litigation")
    expected, _ = eq.brief(text, budget=1)
    actual = build_graph(profile="litigation", log_path=None).invoke({"raw_draft": text, "budget": 1})
    assert actual["brief"] == expected and actual["status"] == Status.BUDGET_PROTECTED_OVERFLOW


def test_request_state_is_fresh_and_log_is_allowlisted(tmp_path):
    base = Parts()
    graph = build_graph(parts=base, log_path=tmp_path / "trace.jsonl")
    request = {"raw_draft": "합성 전화 010-0000-0000. 핵심은 비용이다."}
    original = deepcopy(request)
    first = graph.invoke(request)
    second = graph.invoke({"raw_draft": "[BLOCK] 다른 요청"})
    assert request == original and first["rows"] and second["rows"] == [] and base.rules is None
    lines = (tmp_path / "trace.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2 and all(set(json.loads(line)) == ALLOWED for line in lines)
    assert "010-0000-0000" not in "".join(lines) and request["raw_draft"] not in "".join(lines)


@pytest.fixture
def armed_tracing(monkeypatch):
    import langsmith.utils as utils
    from langsmith import Client
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2_fake_key_for_test")
    monkeypatch.setenv("LANGSMITH_ENDPOINT", "http://127.0.0.1:9")
    utils.get_env_var.cache_clear()
    calls = []
    for name in ("create_run", "update_run", "batch_ingest_runs", "multipart_ingest", "_create_run", "_update_run", "_post_batch_ingest_runs", "_multipart_ingest_ops"):
        if hasattr(Client, name):
            monkeypatch.setattr(Client, name, lambda self, *a, _name=name, **kw: calls.append(_name))
    original = socket.socket.connect
    def connect(self, address, *a, **kw):
        if isinstance(address, tuple) and address[0] == "127.0.0.1" and address[1] != 9:
            return original(self, address, *a, **kw)
        calls.append("socket")
        raise OSError("test blocked upload")
    monkeypatch.setattr(socket.socket, "connect", connect)
    yield calls
    utils.get_env_var.cache_clear()


def test_serving_guard_covers_entire_sync_and_async_graph(armed_tracing):
    graph = build_graph(log_path=None)
    graph.invoke({"raw_draft": "합성 자료다."})
    async def run():
        a, b = await asyncio.gather(graph.ainvoke({"raw_draft": "첫 합성 입력이다."}),
                                    graph.ainvoke({"raw_draft": "[BLOCK] 둘째 입력"}))
        assert a["status"] == Status.OK and b["status"] == Status.BLOCKED
    asyncio.run(run())
    from langchain_core.tracers.langchain import wait_for_all_tracers
    wait_for_all_tracers()
    assert armed_tracing == []
