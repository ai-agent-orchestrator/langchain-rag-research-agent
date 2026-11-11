"""Domain filter contract, research filter rules and the screen/verify gates in the guardrail graph."""
import asyncio

import pytest

from rag_research_agent.core.types import Status
from rag_research_agent.guard.domain_filter import DomainFilter, InputDecision, Verdict, get_filter, registered
from rag_research_agent.guard.research_filter import ResearchFilter
from rag_research_agent.rag.guardrail_graph import GuardrailLimits, GuardrailRunner, route_after_verify
from rag_research_agent.rag.guidance import GuidanceReply

EVIDENCE = ("금리 인상 때문에 2025년 주택 거래량이 18% 감소했다. 다만 수도권 신축은 제외된다.",
            "거래 감소는 중개업 매출 하락으로 이어졌다.")
GOOD = "금리 인상 때문에 2025년 주택 거래량이 18% 감소했다. 다만 수도권 신축은 제외된다."
REQUEST = {"caseType": "OTHER", "coreStatement": "금리 인상이 주택 거래량에 준 영향과 예외 조건을 정리해 주세요."}


def test_research_filter_is_registered_and_satisfies_the_contract():
    assert "research" in (registered() or ()) or get_filter("research")
    f = get_filter("research")
    assert isinstance(f, DomainFilter) and f.name == "research" and f.version
    assert isinstance(f.check_input("질문"), InputDecision)
    assert isinstance(f.verify("답", EVIDENCE), Verdict)
    assert isinstance(f.finalize("답"), str)


def test_unknown_filter_names_the_registered_ones():
    with pytest.raises(KeyError, match="research"):
        get_filter("nope")


def test_input_screen_blocks_empty_and_too_long():
    f = ResearchFilter(max_input_chars=50)
    assert f.check_input("  ").code == "EMPTY_INPUT"
    assert f.check_input("가" * 51).code == "INPUT_TOO_LONG"
    assert f.check_input("금리와 거래량").allowed


def test_grounded_answer_with_causality_and_constraint_passes():
    verdict = ResearchFilter().verify(GOOD, EVIDENCE)
    assert verdict.ok, verdict.codes
    assert dict(verdict.scores)["density"] >= 0.5


def test_number_not_in_source_is_flagged():
    verdict = ResearchFilter().verify(GOOD.replace("18%", "27%"), EVIDENCE)
    assert "UNSUPPORTED_NUMBER" in verdict.codes and verdict.retryable


def test_dropped_causality_and_constraint_are_flagged():
    verdict = ResearchFilter().verify("2025년 주택 거래량이 18% 감소했다.", EVIDENCE)
    assert {"CAUSAL_LOSS", "CONSTRAINT_DROPPED"} <= set(verdict.codes)


def test_generic_summary_is_low_density():
    verdict = ResearchFilter().verify("일반적으로 다양한 요인이 중요하다. 여러 가지 측면을 종합적으로 봐야 한다.", EVIDENCE)
    assert "LOW_DENSITY" in verdict.codes


def test_no_evidence_is_not_retryable():
    verdict = ResearchFilter().verify(GOOD, ())
    assert verdict.codes == ("NO_EVIDENCE",) and not verdict.retryable


def test_citation_markers_are_not_numbers():
    assert ResearchFilter().verify(GOOD + " [1]", EVIDENCE).ok


def _run(rag, **kw):
    return asyncio.run(GuardrailRunner(rag, domain=ResearchFilter(), **kw).ainvoke(REQUEST))


def _ok(text):
    return GuidanceReply(Status.OK, text, model="fake", generation_calls=1)


def test_graph_passes_a_verified_answer():
    async def rag(_):
        return _ok(GOOD), EVIDENCE
    result = _run(rag)
    assert result.reply.answer == GOOD and result.verify_codes == ()
    assert result.path == ("classify", "screen", "rag", "verify", "finish")
    assert result.domain == "research" and result.domain_log == ("SCREEN:PASS", "VERIFY:PASS")


def test_graph_regenerates_once_then_passes():
    answers = iter([GOOD.replace("18%", "27%"), GOOD])

    async def rag(_):
        return _ok(next(answers)), EVIDENCE
    result = _run(rag)
    assert result.reply.answer == GOOD and result.loops == 2 and result.verify_rounds == 2
    assert result.domain_log[1].startswith("VERIFY:FAIL:UNSUPPORTED_NUMBER") and result.domain_log[-1] == "VERIFY:PASS"


def test_graph_never_returns_text_that_keeps_failing():
    async def rag(_):
        return _ok("일반적으로 다양한 요인이 중요하다."), EVIDENCE
    result = _run(rag, limits=GuardrailLimits(max_loops=3, max_verify_rounds=2))
    assert result.reply.status == Status.REQUEST_MORE and result.reply.reason_code == "VERIFY_FAILED"
    assert "다양한" not in result.reply.answer
    assert result.loops == 3 and result.stop_code == ""


def test_not_retryable_issue_returns_safe_answer_without_regenerating():
    async def rag(_):
        return _ok(GOOD)              # no evidence passed to the verifier
    result = _run(rag)
    assert result.loops == 1 and result.reply.reason_code == "VERIFY_FAILED"


def test_screen_block_skips_rag():
    calls = []

    async def rag(_):
        calls.append(1)
        return _ok(GOOD), EVIDENCE
    runner = GuardrailRunner(rag, domain=ResearchFilter(max_input_chars=12))
    result = asyncio.run(runner.ainvoke(REQUEST))
    assert not calls and result.reply.status == Status.BLOCKED and result.reply.reason_code == "INPUT_TOO_LONG"
    assert result.path == ("classify", "screen", "finish")


def test_request_more_replies_are_not_verified():
    async def rag(_):
        return GuidanceReply(Status.REQUEST_MORE, "자료가 없습니다."), ()
    result = _run(rag)
    assert "verify" not in result.path and result.reply.status == Status.REQUEST_MORE


def test_domain_log_holds_codes_only():
    async def rag(_):
        return _ok(GOOD.replace("18%", "27%")), EVIDENCE
    result = _run(rag)
    assert all(entry.split(":")[0] in {"SCREEN", "VERIFY"} for entry in result.domain_log)
    assert not any("금리" in entry for entry in result.domain_log)


def test_route_after_verify_is_pure():
    limits = GuardrailLimits(max_loops=3, max_verify_rounds=1)
    base = {"verify_codes": ("LOW_DENSITY",), "verify_retryable": True, "loop_counter": 1, "cost_units": 1.0}
    assert route_after_verify({**base, "verify_rounds": 1}, limits) == "retry"
    assert route_after_verify({**base, "verify_rounds": 2}, limits) == "finish"
    assert route_after_verify({**base, "verify_rounds": 1, "cost_units": 99.0}, limits) == "finish"
    assert route_after_verify({**base, "verify_codes": ()}, limits) == "finish"


def test_without_domain_the_graph_is_unchanged():
    async def rag(_):
        return _ok("아무 답")
    result = asyncio.run(GuardrailRunner(rag).ainvoke(REQUEST))
    assert result.path == ("classify", "rag", "finish") and result.reply.answer == "아무 답"
