"""Synthetic path tests through the real retry graph, Chroma library and guardrail."""
import asyncio
from dataclasses import replace

import pytest

from rag_research_agent.core.types import Status
from rag_research_agent.rag.guidance import GuidanceReply
from rag_research_agent.rag.guardrail_graph import GuardrailLimits, GuardrailRunner, default_cost
from rag_research_agent.rag.retry_graph import build_graph


QUERY = "alpha 2026, alpha 2026"
REQUEST = {"caseType": "CIVIL", "coreStatement": QUERY}


@pytest.fixture
def library(tmp_path):
    from rag_research_agent.embed.providers import FakeEmbedder
    from rag_research_agent.rag.library import Library

    return Library(tmp_path / "library", embedder=FakeEmbedder(64)).build(
        [("synthetic", "Synthetic evidence", "contract evidence")])


def test_three_retrievals_are_reported_and_reset_per_invocation(library):
    graph = build_graph(library, mode="lex", tau=1.0)
    for _ in range(2):
        state = graph.invoke({"query": QUERY, "retrieval_calls": 999})
        assert state["status"] == Status.REQUEST_MORE
        assert len(state["attempts"]) == 3
        assert state["retrieval_calls"] == 3
        assert state["generation_calls"] == 0


def test_each_subquestion_search_is_charged(library):
    state = build_graph(library, mode="lex", tau=1.0, max_retries=1).invoke(
        {"query": "alpha, beta"})
    assert len(state["attempts"]) == 2
    assert [len(a["queries"]) for a in state["attempts"]] == [1, 2]
    assert state["retrieval_calls"] == 3


@pytest.mark.parametrize("query,tau,retries", [
    ("contract evidence", 0.0, 2),  # immediate success, including Equalizer stages
    (QUERY, 1.0, 0),                 # retry disabled
    ("alpha", 1.0, 2),             # no unused rewrite variants
])
def test_single_retrieval_paths_keep_the_original_cost(library, query, tau, retries):
    state = build_graph(library, mode="lex", tau=tau, max_retries=retries).invoke({"query": query})
    assert len(state["attempts"]) == state["retrieval_calls"] == 1
    reply = GuidanceReply(state["status"], state["final_prompt_input"],
                          generation_calls=state["generation_calls"], retrieval_calls=state["retrieval_calls"])
    assert default_cost(reply) == pytest.approx(0.1)


@pytest.mark.parametrize("limit,stop", [(1.0, ""), (0.3, ""), (0.2, "COST_LIMIT")])
def test_real_retry_graph_cost_reaches_guardrail(library, limit, stop):
    graph = build_graph(library, mode="lex", tau=1.0)
    states = []

    async def rag(request):
        state = await graph.ainvoke({"query": request["coreStatement"]})
        states.append(state)
        # E2 returns a state dict; carry its counters across the GuidanceReply boundary.
        return GuidanceReply(state["status"], state["final_prompt_input"],
                             generation_calls=state["generation_calls"], retrieval_calls=state["retrieval_calls"])

    result = asyncio.run(GuardrailRunner(rag, limits=GuardrailLimits(max_cost=limit)).ainvoke(REQUEST))
    assert len(states) == 1 and states[0]["retrieval_calls"] == 3
    assert result.loops == 1 and result.cost_units == pytest.approx(0.3)
    assert result.stop_code == stop
    assert result.path[-1] == ("kill" if stop else "finish")
    if stop:
        assert result.reply is None
    else:
        assert result.reply.retrieval_calls == 3


def test_generation_cost_is_added_and_serialization_is_unchanged():
    original = GuidanceReply(Status.OK, "Synthetic answer", generation_calls=1)
    retried = replace(original, retrieval_calls=3)
    assert original.retrieval_calls == 1
    assert default_cost(original) == pytest.approx(1.1)
    assert default_cost(retried) == pytest.approx(1.3)
    assert default_cost(None) == pytest.approx(0.1)
    assert retried.to_dict() == original.to_dict() == {
        "answer": "Synthetic answer", "model": original.model,
        "evidenceStatus": "NOT_FOUND", "citationIds": [],
    }
    blocked = GuidanceReply(Status.BLOCKED, "Blocked", reason_code="SYNTHETIC")
    assert replace(blocked, retrieval_calls=3).to_dict() == blocked.to_dict() == {
        "blocked": True, "reasonCode": "SYNTHETIC", "answer": "Blocked",
    }
