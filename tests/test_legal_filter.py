"""Synthetic rule and real GuardrailRunner substitution tests; no model or network."""
import asyncio

import pytest

from rag_research_agent.core.types import Status
from rag_research_agent.guard.domain_filter import BUILTINS, DomainFilter, InputDecision, Verdict, get_filter, registered
from rag_research_agent.guard.legal_filter import DISCLAIMER, LegalFilter
from rag_research_agent.guard.research_filter import ResearchFilter
from rag_research_agent.rag.guardrail_graph import GuardrailLimits, GuardrailRunner, RouteDecision
from rag_research_agent.rag.guidance import GuidanceReply

EVIDENCE = ("합성규정 제1조: 2025-01-02 접수. 2025-02-03 통지.",)
GOOD = "제1조에 따라 2025년 1월 2일 접수, 2025년 2월 3일 통지."
REQUEST = {"caseType": "OTHER", "coreStatement": "민사 계약에 관한 합성 사건의 절차를 정리해 주세요."}


@pytest.mark.parametrize("name", ["research", "legal"])
def test_registered_filters_satisfy_common_contract(name):
    assert name in registered() or get_filter(name)
    domain = get_filter(name)
    assert isinstance(domain, DomainFilter) and domain.name == name and domain.version
    assert isinstance(domain.check_input("질문"), InputDecision)
    assert isinstance(domain.verify("답", EVIDENCE), Verdict)
    assert isinstance(domain.finalize("답"), str)
    assert BUILTINS[name] == type(domain).__module__


@pytest.mark.parametrize(("text", "branch"), [
    ("형사 고소", "criminal"), ("폭행 사건", "criminal"),
    ("민사 계약", "civil"), ("임대차 분쟁", "civil"),
    ("가사 이혼", "family"), ("상속 문의", "family"),
    ("기타 문의", "other"), ("분류할 단어 없음", "other"),
    ("이혼과 손해배상", "family"), ("형사 민사 가사", "criminal"),
])
def test_input_branches(text, branch):
    decision = LegalFilter().check_input(text)
    assert decision.allowed and decision.code == "" and decision.branch == branch


@pytest.mark.parametrize("text", ["", " \n\t"])
def test_empty_input_is_blocked(text):
    assert LegalFilter().check_input(text) == InputDecision(False, "EMPTY_INPUT")


def test_grounded_answer_passes_with_normalized_dates():
    assert LegalFilter().verify(GOOD, EVIDENCE).ok


def test_unsupported_statutes_count_unique_exact_article_numbers():
    verdict = LegalFilter().verify("제1조 제2조 제2조 제3조", ("제10조",))
    assert verdict.codes == ("UNSUPPORTED_STATUTE",) and verdict.retryable
    assert verdict.issues[0].count == 3


@pytest.mark.parametrize("status", ["폐지", "삭제", "구법"])
@pytest.mark.parametrize("prefix", [True, False])
def test_repealed_status_before_or_after_article(status, prefix):
    source = f"{status} 제1조" if prefix else f"제1조 ({status})"
    verdict = LegalFilter().verify("제1조 인용", (source,))
    assert verdict.codes == ("REPEALED_CITED",) and verdict.retryable


def test_status_does_not_leak_to_another_clause_or_document():
    evidence = ("제1조 삭제. 제2조 현행.", "제3조 현행.")
    assert LegalFilter().verify("제2조 제3조", evidence).ok


def test_uncited_repealed_article_is_not_flagged():
    assert LegalFilter().verify("제2조", ("제1조 구법; 제2조 현행",)).ok


def test_reversed_shared_dates_are_flagged_across_sources():
    verdict = LegalFilter().verify("2025-02-03 통지 후 2025-01-02 접수.", EVIDENCE)
    assert verdict.codes == ("TIMELINE_MIXED",) and verdict.retryable
    assert LegalFilter().verify("2025-02-03 다음 2025-01-02", ("2025-01-02", "2025-02-03")).codes == verdict.codes


@pytest.mark.parametrize("answer", ["2025-02-03 통지.", "날짜 없는 설명.",
                                  "2025-01-02 접수 후 2025-02-03 통지, 2025-01-02는 접수일."])
def test_partial_or_repeated_dates_do_not_reverse_order(answer):
    assert LegalFilter().verify(answer, EVIDENCE).ok


def test_invalid_dates_are_ignored_and_order_follows_evidence_mentions():
    assert LegalFilter().verify("2025-02-30 다음 2025-01-02", ("2025-01-02 다음 2025-02-30",)).ok
    assert LegalFilter().verify("2025-02-03 다음 2025-01-02", ("2025-02-03 다음 2025-01-02",)).ok


@pytest.mark.parametrize("evidence", [(), ("  ",)])
def test_no_evidence_is_not_retryable(evidence):
    verdict = LegalFilter().verify(GOOD, evidence)
    assert verdict.codes == ("NO_EVIDENCE",) and not verdict.retryable


def test_empty_answer_can_be_retried():
    verdict = LegalFilter().verify("  ", EVIDENCE)
    assert verdict.codes == ("EMPTY_ANSWER",) and verdict.retryable


def test_all_issues_have_codes_and_counts_without_source_text():
    verdict = LegalFilter().verify("제1조 제2조 2025-02-03 다음 2025-01-02", EVIDENCE + ("제1조 삭제",))
    assert verdict.codes == ("UNSUPPORTED_STATUTE", "REPEALED_CITED", "TIMELINE_MIXED")
    assert all(issue.count == 1 and issue.retryable for issue in verdict.issues)
    assert "제1조" not in repr(verdict)


def test_finalize_appends_notice():
    assert LegalFilter().finalize(GOOD, "civil") == GOOD + "\n\n" + DISCLAIMER


def test_same_real_graph_accepts_legal_and_research_filters():
    async def rag(_):
        return GuidanceReply(Status.OK, GOOD), EVIDENCE

    legal = asyncio.run(GuardrailRunner(rag, domain=get_filter("legal")).ainvoke(REQUEST))
    assert legal.path == ("classify", "screen", "rag", "verify", "finish")
    assert legal.domain == "legal" and legal.branch == "civil"
    assert legal.reply.answer == GOOD + "\n\n" + DISCLAIMER
    assert legal.domain_log == ("SCREEN:PASS", "VERIFY:PASS")
    text = "금리 인상 때문에 거래가 감소했다. 다만 특정 지역은 제외한다."

    async def research_rag(_):
        return GuidanceReply(Status.OK, text), (text,)

    research = asyncio.run(GuardrailRunner(research_rag, domain=ResearchFilter()).ainvoke(REQUEST))
    assert research.path == legal.path and research.reply.answer == text
    assert research.domain == "research"
    default = asyncio.run(GuardrailRunner(rag).ainvoke(REQUEST))
    assert default.path == ("classify", "rag", "finish") and default.reply.answer == GOOD


def test_graph_retries_then_finalizes_only_verified_answer():
    answers = iter(["제2조", GOOD])

    async def rag(_):
        return GuidanceReply(Status.OK, next(answers)), EVIDENCE

    result = asyncio.run(GuardrailRunner(rag, domain=LegalFilter()).ainvoke(REQUEST))
    assert result.loops == 2 and result.verify_rounds == 2 and result.verify_codes == ()
    assert result.domain_log == ("SCREEN:PASS", "VERIFY:FAIL:UNSUPPORTED_STATUTE", "VERIFY:PASS")
    assert result.reply.answer == GOOD + "\n\n" + DISCLAIMER


def test_graph_keeps_failed_answer_private_when_budget_exhausted():
    async def rag(_):
        return GuidanceReply(Status.OK, "제2조"), EVIDENCE

    result = asyncio.run(GuardrailRunner(rag, domain=LegalFilter(),
                                       limits=GuardrailLimits(max_loops=1)).ainvoke(REQUEST))
    assert result.reply.status == Status.REQUEST_MORE and result.reply.reason_code == "VERIFY_FAILED"
    assert "제2조" not in result.reply.answer and DISCLAIMER not in result.reply.answer


def test_empty_screen_skips_rag_when_classification_reaches_screen():
    calls = []

    async def rag(_):
        calls.append(1)
        return GuidanceReply(Status.OK, GOOD), EVIDENCE

    runner = GuardrailRunner(rag, domain=LegalFilter(), router=lambda _: RouteDecision(route="research"))
    result = asyncio.run(runner.ainvoke({"coreStatement": " "}))
    assert not calls and result.reply.status == Status.BLOCKED and result.reply.reason_code == "EMPTY_INPUT"
    assert result.path == ("classify", "screen", "finish")
