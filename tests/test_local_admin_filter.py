"""Fictional administration cases through real domain contracts and guardrail graph."""
import asyncio

import pytest

from rag_research_agent.core.types import Status
from rag_research_agent.guard.domain_filter import BUILTINS, DomainFilter, InputDecision, Verdict, get_filter, registered
from rag_research_agent.guard.legal_filter import LegalFilter
from rag_research_agent.guard.local_admin_filter import LocalAdminFilter, NOTICE
from rag_research_agent.guard.medical_filter import MedicalFilter
from rag_research_agent.guard.research_filter import ResearchFilter
from rag_research_agent.rag.guardrail_graph import GuardrailLimits, GuardrailRunner, RouteDecision
from rag_research_agent.rag.guidance import GuidanceReply

EVIDENCE = ("개정 양식 v2, 시행일 2026-01-02.\n지역 예외: 가람시 산간 사업장은 현장 접수.\n"
            "필수 구비서류: 신청서, 사업계획서, 배치도.",)
GOOD = "양식 v2를 사용하세요. 가람시 산간 사업장은 현장 접수. 신청서, 사업계획서, 배치도를 준비하세요."
REQUEST = {"caseType": "OTHER", "coreStatement": "가람시 사업 허가 신청의 양식과 필수 구비서류를 정리해 주세요."}


@pytest.mark.parametrize("name", ["research", "legal", "medical", "local_admin"])
def test_common_contract_for_registered_domains(name):
    assert {ResearchFilter.name, LegalFilter.name, MedicalFilter.name, LocalAdminFilter.name} <= set(registered())
    domain = get_filter(name)
    assert isinstance(domain, DomainFilter) and domain.name == name and domain.version
    assert isinstance(domain.check_input("가람시 합성 신청"), InputDecision)
    assert isinstance(domain.verify("합성 답", EVIDENCE), Verdict)
    assert isinstance(domain.finalize("합성 답"), str)
    assert BUILTINS[name] == type(domain).__module__


@pytest.mark.parametrize(("text", "branch"), [
    ("가람시 허가 신청", "garam:permit"), ("누리군 등록", "nuri:registration"),
    ("다온구 신고", "daon:registration"), ("가람시 허가 갱신", "garam:renewal"),
    ("가람시 변경 허가", "garam:change"), ("가람시 폐업 변경", "garam:closure"),
    ("가람시 신청", "garam:application"), ("가람시 문의", "garam:other"),
])
def test_jurisdiction_and_application_branch(text, branch):
    assert LocalAdminFilter().check_input(text) == InputDecision(True, branch=branch)


@pytest.mark.parametrize(("text", "code"), [(" \n", "EMPTY_INPUT"),
    ("허가 신청", "JURISDICTION_REQUIRED"), ("가람시 누리군 허가", "JURISDICTION_AMBIGUOUS")])
def test_screen_rejects_empty_missing_or_ambiguous_jurisdiction(text, code):
    assert LocalAdminFilter().check_input(text) == InputDecision(False, code)


def test_jurisdiction_keywords_can_be_injected_without_input_echo():
    domain = LocalAdminFilter(jurisdictions=(("마루시", "maru"),))
    assert domain.check_input("마루시 신청").branch == "maru:application"
    assert not domain.check_input("가람시 신청").allowed


@pytest.mark.parametrize("marker", ["개정", "시행일"])
@pytest.mark.parametrize("kind", ["양식", "서식", "기준"])
def test_old_numeric_version_is_retryable(marker, kind):
    verdict = LocalAdminFilter().verify(f"{kind} v1을 사용하세요.", (f"{marker}: {kind} v2",))
    assert verdict.codes == ("OUTDATED_FORM",) and verdict.retryable


def test_latest_version_is_independent_of_source_order_and_kind():
    domain = LocalAdminFilter()
    evidence = ("개정 양식 v3", "개정 양식 v2", "개정 기준 v5")
    assert domain.verify("양식 v3, 기준 v5", evidence).ok
    verdict = domain.verify("양식 v2, 양식 v2, 기준 v4", evidence)
    assert verdict.codes == ("OUTDATED_FORM",) and verdict.issues[0].count == 2
    assert domain.verify("기준 v1", ("개정 양식 v2",)).ok
    assert domain.verify("양식 v1.", ("개정 양식 v2.",)).codes == ("OUTDATED_FORM",)


@pytest.mark.parametrize("answer", ["양식 v1을 사용", "양식 v2를 사용", "구양식을 사용", "이전 기준을 적용"])
def test_no_revision_status_leaks_across_clauses_or_sources(answer):
    assert LocalAdminFilter().verify(answer, ("개정", "양식 v3. 기준 v2")).ok
    assert LocalAdminFilter().verify(answer, ("개정. 양식 v3. 기준 v2",)).ok


@pytest.mark.parametrize("old", ["구양식", "이전 양식", "구서식", "이전 기준"])
def test_explicit_old_form_or_criteria_advice(old):
    assert LocalAdminFilter().verify(old + "을 사용", ("개정 양식 v2, 기준 v3",)).codes == ("OUTDATED_FORM",)


def test_valid_dated_versions_normalize_and_invalid_dates_are_ignored():
    domain = LocalAdminFilter()
    evidence = ("양식 시행일 2026년 1월 2일",)
    assert domain.verify("양식 2026-01-02", evidence).ok
    assert domain.verify("양식 2025-12-01", evidence).codes == ("OUTDATED_FORM",)
    assert domain.verify("양식 2025-12-01", ("양식 시행일 2026-02-30",)).ok


@pytest.mark.parametrize("prefix", ["지역 예외:", "가람시 예외:", "다만"])
def test_exception_content_must_be_present(prefix):
    evidence = (prefix + " 가람시 산간 사업장은 현장 접수.",)
    domain = LocalAdminFilter()
    assert domain.verify("가람시 산간 사업장은 현장 접수.", evidence).ok
    verdict = domain.verify("지역 예외를 확인하세요.", evidence)
    assert verdict.codes == ("LOCAL_EXCEPTION_DROPPED",) and verdict.retryable


def test_all_distinct_exceptions_are_required_and_not_cross_document():
    domain = LocalAdminFilter()
    text = "지역 예외: 가람시 산간은 방문.\n지역 예외: 누리군 도서는 우편."
    verdict = domain.verify("가람시 산간은 방문.", (text, text))
    assert verdict.issues[0].count == 1
    assert domain.verify("합성 답", ("지역 예외:", "현장 접수")).ok


@pytest.mark.parametrize("listing", ["신청서, 배치도·동의서", "\n- 신청서\n* 배치도\n• 동의서"])
def test_inline_and_bullet_checklists_require_every_item(listing):
    evidence = ("필수 구비서류: " + listing,)
    domain = LocalAdminFilter()
    assert domain.verify("동의서, 신청서 및 배치도", evidence).ok
    verdict = domain.verify("신청서", evidence)
    assert verdict.codes == ("CHECKLIST_INCOMPLETE",) and verdict.issues[0].count == 2


def test_checklist_duplicates_normalization_and_boundaries():
    domain = LocalAdminFilter()
    evidence = ("필수 구비서류: 사업 계획서, 배치도, 배치도. 선택 서류: 안내문",)
    assert domain.verify("사업계획서 배치도", evidence).ok
    assert domain.verify("배치도", evidence).issues[0].count == 1
    assert domain.verify("합성 답", ("필수 구비서류:", "배치도")).ok
    assert domain.verify("합성 답", ("선택 서류: 안내문",)).ok


@pytest.mark.parametrize("evidence", [(), (" \n",)])
def test_no_evidence_is_not_retryable(evidence):
    verdict = LocalAdminFilter().verify(GOOD, evidence)
    assert verdict.codes == ("NO_EVIDENCE",) and not verdict.retryable


def test_empty_answer_combined_codes_and_final_notice():
    domain = LocalAdminFilter()
    assert domain.verify(" ", EVIDENCE).codes == ("EMPTY_ANSWER",)
    assert domain.verify(GOOD, EVIDENCE).ok
    verdict = domain.verify("양식 v1을 사용하세요.", EVIDENCE)
    assert verdict.codes == ("OUTDATED_FORM", "LOCAL_EXCEPTION_DROPPED", "CHECKLIST_INCOMPLETE")
    assert verdict.retryable and verdict.issues[-1].count == 3
    assert "가람시" not in repr(verdict) and "신청서" not in repr(verdict)
    assert domain.finalize(GOOD) == GOOD + "\n\n" + NOTICE
    assert "담당 기관 확인" in NOTICE


def _run(rag, request=REQUEST, **kwargs):
    runner = GuardrailRunner(rag, domain=get_filter("local_admin"),
                             router=lambda _: RouteDecision(route="research"), **kwargs)
    return asyncio.run(runner.ainvoke(request))


def test_real_graph_passes_and_finalizes_opt_in_filter():
    async def rag(_):
        return GuidanceReply(Status.OK, GOOD), EVIDENCE

    result = _run(rag)
    assert result.reply.answer == GOOD + "\n\n" + NOTICE
    assert result.branch == "garam:permit" and result.domain == "local_admin"
    assert result.domain_log == ("SCREEN:PASS", "VERIFY:PASS")
    default = asyncio.run(GuardrailRunner(rag).ainvoke(REQUEST))
    assert default.path == ("classify", "rag", "finish") and default.reply.answer == GOOD


def test_real_graph_blocks_missing_jurisdiction_before_rag():
    async def rag(_):
        pytest.fail("Blocked inputs must not invoke RAG")

    result = _run(rag, {"coreStatement": "허가 신청"})
    assert result.reply.status == Status.BLOCKED and result.loops == 0
    assert result.domain_log == ("SCREEN:BLOCK:JURISDICTION_REQUIRED",)


def test_real_graph_retries_then_passes():
    answers = iter([GOOD.replace("v2", "v1"), GOOD])

    async def rag(_):
        return GuidanceReply(Status.OK, next(answers)), EVIDENCE

    result = _run(rag)
    assert result.loops == 2 and result.reply.answer == GOOD + "\n\n" + NOTICE
    assert result.domain_log == ("SCREEN:PASS", "VERIFY:FAIL:OUTDATED_FORM", "VERIFY:PASS")


def test_real_graph_never_returns_answer_that_keeps_failing():
    async def rag(_):
        return GuidanceReply(Status.OK, "양식 v1을 사용"), EVIDENCE

    result = _run(rag, limits=GuardrailLimits(max_loops=2, max_verify_rounds=1))
    assert result.loops == 2 and result.reply.reason_code == "VERIFY_FAILED"
    assert "v1" not in result.reply.answer and NOTICE not in result.reply.answer


def test_real_graph_missing_evidence_stops_without_retry():
    async def rag(_):
        return GuidanceReply(Status.OK, GOOD), ()

    result = _run(rag)
    assert result.loops == 1 and result.reply.reason_code == "VERIFY_FAILED"
    assert result.domain_log == ("SCREEN:PASS", "VERIFY:FAIL:NO_EVIDENCE")
