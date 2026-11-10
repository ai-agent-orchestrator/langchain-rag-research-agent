"""LangGraph guardrail: classify -> rag -> cost/loop/health edge -> finish | kill."""
import asyncio

import pytest
from pydantic import ValidationError

from test_equalizer_graph import armed_tracing  # noqa: F401  (fixture: tracing env armed, uploads must stay 0)
from test_guidance_bridge import Model, REQUEST, SearchLibrary, draft, pipeline
from rag_research_agent.core.contracts import RetrievalUnavailable
from rag_research_agent.core.types import Status
from rag_research_agent.rag.answer import DraftRejected
from rag_research_agent.rag.execution import InferenceTimeout
from rag_research_agent.rag.guardrail_graph import (
    GuardrailLimits, GuardrailRunner, RouteDecision, SMALLTALK_ANSWER, route_by_cost_and_health,
    rule_router, structured_router,
)
from rag_research_agent.rag.guidance import GuidanceReply
from rag_research_agent.rag.http_mapping import map_outcome

RESEARCH = {"caseType": "CIVIL", "coreStatement": "임대차 계약 해지 후 보증금을 돌려받지 못했습니다."}


def ok_reply(calls=1):
    return GuidanceReply(Status.OK, "안내", "m", generation_calls=calls)


class Rag:
    """Scripted RAG node: each call pops the next outcome (a reply or an exception)."""
    def __init__(self, *outcomes):
        self.outcomes, self.calls = list(outcomes), 0

    async def __call__(self, request):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def run(runner, request=RESEARCH):
    return asyncio.run(runner.ainvoke(request))


def test_research_request_goes_through_rag_and_finishes():
    rag = Rag(ok_reply())
    result = run(GuardrailRunner(rag))
    assert result.route == "research" and result.path == ("classify", "rag", "finish")
    assert result.reply.status == Status.OK and result.stop_code == "" and rag.calls == 1
    assert result.loops == 1 and result.cost_units == pytest.approx(1.1)
    assert map_outcome(result)[0] == 200


@pytest.mark.parametrize("text", ["안녕", "hi there", "  ", "테스트 입니다"])
def test_smalltalk_never_reaches_rag_and_makes_no_generation(text):
    rag = Rag()
    result = run(GuardrailRunner(rag), {"caseType": "CIVIL", "coreStatement": text})
    assert rag.calls == 0 and result.path == ("classify", "finish")
    assert result.reply.status == Status.REQUEST_MORE and result.reply.answer == SMALLTALK_ANSWER
    assert result.reply.generation_calls == 0


def test_transient_failure_is_retried_then_succeeds():
    rag = Rag(RetrievalUnavailable("down"), ok_reply())
    result = run(GuardrailRunner(rag))
    assert rag.calls == 2 and result.path == ("classify", "rag", "rag", "finish")
    assert result.reply.status == Status.OK and result.error_code == ""


def test_retries_stop_at_the_loop_limit_and_report_the_real_cause():
    rag = Rag(*[RetrievalUnavailable("down")] * 5)
    result = run(GuardrailRunner(rag, limits=GuardrailLimits(max_loops=3)))
    assert rag.calls == 3 and result.stop_code == "LOOP_LIMIT" and result.reply is None
    assert result.error_code == "RETRIEVAL_UNAVAILABLE"
    status, body, headers = map_outcome(result)
    assert (status, body, headers["Retry-After"]) == (503, {"error": "RETRIEVAL_UNAVAILABLE"}, "30")


def test_cost_limit_kills_the_session():
    rag = Rag(ok_reply(calls=20))
    result = run(GuardrailRunner(rag, limits=GuardrailLimits(max_cost=15.0)))
    assert result.stop_code == "COST_LIMIT" and result.path[-1] == "kill" and result.reply is None
    assert map_outcome(result)[:2] == (503, {"error": "GUARDRAIL_STOPPED"})


def test_non_transient_error_is_not_retried():
    rag = Rag(DraftRejected("bad citation"), ok_reply())
    result = run(GuardrailRunner(rag))
    assert rag.calls == 1 and result.stop_code == "NODE_ERROR" and result.error_code == "AI_DRAFT_REJECTED"
    assert map_outcome(result)[:2] == (502, {"error": "AI_DRAFT_REJECTED"})


def test_unexpected_exception_is_contained_and_maps_to_500():
    rag = Rag(ZeroDivisionError("boom 010-1234-5678"))
    result = run(GuardrailRunner(rag))
    assert result.stop_code == "NODE_ERROR"
    status, body, _ = map_outcome(result)
    assert (status, body) == (500, {"error": "INTERNAL_ERROR"}) and "010" not in str(body)


def test_timeout_is_transient():
    rag = Rag(InferenceTimeout("slow"), ok_reply())
    assert run(GuardrailRunner(rag)).reply.status == Status.OK and rag.calls == 2


@pytest.mark.parametrize("state,expected", [
    ({"is_buggy": True}, "kill"),
    ({"cost_units": 15.01}, "kill"),
    ({"cost_units": 15.0}, "finish"),
    ({"transient": True, "loop_counter": 2}, "retry"),
    ({"transient": True, "loop_counter": 3}, "kill"),
    ({}, "finish"),
])
def test_gate_two_is_a_pure_function(state, expected):
    assert route_by_cost_and_health(state, GuardrailLimits(max_loops=3, max_cost=15.0)) == expected


def test_limits_are_validated():
    with pytest.raises(ValueError):
        GuardrailLimits(max_loops=0)
    with pytest.raises(ValueError):
        GuardrailLimits(max_cost=0)


def test_rule_router_is_conservative():
    assert rule_router("안녕하세요").route == "smalltalk"
    assert rule_router("안녕하세요, 전세 보증금 반환 소송 절차가 궁금합니다. 계약은 2024년에 했습니다.").route == "research"
    assert rule_router("임대차 보증금 반환").route == "research"


class StructuredModel:
    """Stands in for a chat model's with_structured_output(); records exactly what it was sent."""
    def __init__(self, answer):
        self.answer, self.prompts = answer, []

    def with_structured_output(self, schema):
        assert schema is RouteDecision
        return self

    def invoke(self, prompt, config=None):
        self.prompts.append(prompt)
        if isinstance(self.answer, BaseException):
            raise self.answer
        return self.answer


class Masker:
    def mask(self, text):
        return text.replace("010-1234-5678", "[PHONE]")


def test_structured_router_only_sees_masked_text_and_routes():
    model = StructuredModel(RouteDecision(route="smalltalk", reason="model"))
    rag = Rag()
    result = run(GuardrailRunner(rag, router=structured_router(model, Masker())),
                 {"caseType": "CIVIL", "coreStatement": "연락처 010-1234-5678 로 연락 주세요 부탁드립니다"})
    assert result.route == "smalltalk" and rag.calls == 0
    assert "010-1234-5678" not in model.prompts[0] and "[PHONE]" in model.prompts[0]
    assert "<DATA>" in model.prompts[0]


def test_structured_router_falls_back_to_rules_on_model_failure():
    route = structured_router(StructuredModel(RuntimeError("model down")), Masker())
    decision = route("임대차 계약 해지 후 보증금을 돌려받지 못했습니다.")
    assert decision.route == "research" and decision.reason.startswith("fallback:")


def test_structured_router_requires_a_masker():
    with pytest.raises(ValueError):
        structured_router(StructuredModel(RouteDecision(route="research")), None)


def test_route_decision_rejects_unknown_routes():
    with pytest.raises(ValidationError):
        RouteDecision(route="delete_everything")


def test_real_guidance_pipeline_as_the_rag_node_never_traces(armed_tracing):
    async def go():
        model = Model(responses=[draft()])
        p = pipeline(SearchLibrary(), model)
        try:
            runner = GuardrailRunner(p.ainvoke)
            result = await runner.ainvoke(REQUEST)
            assert result.route == "research" and result.reply.status == Status.OK
            assert result.reply.generation_calls == model.calls == 1
            assert result.cost_units == pytest.approx(1.1)
            assert map_outcome(result)[0] == 200
            # the pipeline's own masking still applies inside the node
            assert "010-0000-0000" not in "".join(model.seen)
        finally:
            await p.aclose()
    asyncio.run(go())
    assert armed_tracing == []                      # no LangSmith upload attempt, no socket attempt


def test_real_pipeline_outage_is_retried_then_reported_as_503():
    async def go():
        library = SearchLibrary(RetrievalUnavailable("index down"))
        p = pipeline(library, Model(responses=[draft()]))
        try:
            result = await GuardrailRunner(p.ainvoke, limits=GuardrailLimits(max_loops=2)).ainvoke(REQUEST)
            assert len(library.queries) == 2 and result.stop_code == "LOOP_LIMIT"
            assert map_outcome(result)[0] == 503
        finally:
            await p.aclose()
    asyncio.run(go())
