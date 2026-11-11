"""Synthetic educational cases through real filters and the real graph; no model/network."""
import asyncio

import pytest

from rag_research_agent.core.types import Status
from rag_research_agent.guard.domain_filter import BUILTINS, DomainFilter, InputDecision, Verdict, get_filter, registered
from rag_research_agent.guard.legal_filter import LegalFilter
from rag_research_agent.guard.medical_filter import DISCLAIMER, EMERGENCY_ANSWER, MedicalFilter
from rag_research_agent.guard.research_filter import ResearchFilter
from rag_research_agent.rag.guardrail_graph import GuardrailRunner, RouteDecision
from rag_research_agent.rag.guidance import GuidanceReply

EVIDENCE = ("합성 교육 자료: 약물A는 금기입니다. 약물B 용량은 5 mg입니다.",)
GOOD = "약물A는 금기입니다. 약물B 용량은 5 mg입니다."
REQUEST = {"caseType": "OTHER", "coreStatement": "합성 교육 자료의 약물 금기와 용량을 정리해 주세요."}


@pytest.mark.parametrize("name", ["research", "legal", "medical"])
def test_registered_filters_satisfy_common_contract(name):
    assert {ResearchFilter.name, LegalFilter.name, MedicalFilter.name} <= set(registered())
    domain = get_filter(name)
    assert isinstance(domain, DomainFilter) and domain.name == name and domain.version
    assert isinstance(domain.check_input("합성 질문"), InputDecision)
    assert isinstance(domain.verify("합성 답", EVIDENCE), Verdict)
    assert isinstance(domain.finalize("합성 답"), str)
    assert BUILTINS[name] == type(domain).__module__


@pytest.mark.parametrize("text", ["흉통", "호흡곤란", "호흡 곤란", "의식 저하", "의식소실",
                                 "가슴 통증", "심정지", "심한 출혈"])
def test_emergency_signals_block_at_input(text):
    assert MedicalFilter().check_input(text) == InputDecision(False, "EMERGENCY", "emergency")


def test_fixed_emergency_reply_is_separate_from_finalize():
    assert "즉시 119" in EMERGENCY_ANSWER and "응급실" in EMERGENCY_ANSWER
    assert "119" not in MedicalFilter().finalize(GOOD)


@pytest.mark.parametrize("text", ["", " \n\t"])
def test_empty_input_is_blocked(text):
    assert MedicalFilter().check_input(text) == InputDecision(False, "EMPTY_INPUT")


def test_educational_input_and_grounded_answer_pass():
    assert MedicalFilter().check_input(REQUEST["coreStatement"]).allowed
    assert MedicalFilter().verify(GOOD, EVIDENCE).ok


@pytest.mark.parametrize("answer", ["합성병입니다 확진", "합성병이 확실합니다", "진단이 확실합니다"])
def test_definitive_diagnosis_is_not_retryable(answer):
    verdict = MedicalFilter().verify(answer, ("합성 교육 자료입니다.",))
    assert verdict.codes == ("DEFINITIVE_DIAGNOSIS",) and not verdict.retryable


@pytest.mark.parametrize("answer", ["약물B 용량은 5 mg입니다.", "약물A를 복용하세요.", "약물A는 금기가 아닙니다."])
def test_missing_or_reversed_contraindication_is_flagged(answer):
    verdict = MedicalFilter().verify(answer, EVIDENCE)
    assert verdict.codes == ("CONTRAINDICATION_DROPPED",) and verdict.retryable


def test_contraindications_are_drug_specific_and_counted_once():
    evidence = ("약물A는 금기. 약물C는 금기. 약물C는 금기.",)
    verdict = MedicalFilter().verify("약물A는 금기.", evidence)
    assert verdict.codes == ("CONTRAINDICATION_DROPPED",) and verdict.issues[0].count == 1
    assert MedicalFilter().verify("금기 약물: 약물A", ("약물A는 금기",)).ok
    assert MedicalFilter().verify("금기: 약물A", ("금기: 약물A",)).ok


def test_contraindications_do_not_cross_clauses_or_documents():
    assert MedicalFilter().verify("합성 교육", ("약물A", "금기")).ok
    assert MedicalFilter().verify("합성 교육", ("약물A. 금기",)).ok
    assert MedicalFilter().verify("합성 교육", ("약물A는 금기가 아닙니다.",)).ok


@pytest.mark.parametrize("dose", ["15 mg", "5 g", "2.5 mg", "3 정", "2 캡슐", "4 mL", "8 mcg"])
def test_unsupported_dose_values_and_units(dose):
    verdict = MedicalFilter().verify(f"약물B 용량은 {dose}입니다.", ("약물B 용량은 5 mg입니다.",))
    assert verdict.codes == ("UNSUPPORTED_DOSE",) and verdict.retryable


@pytest.mark.parametrize(("answer", "source"), [("5mg", "5.0 MG"), ("2 mL", "2 ml"),
                                                    ("3 mcg", "3 μg"), ("3 µg", "3 mcg")])
def test_supported_doses_normalize_spacing_case_and_decimal(answer, source):
    assert MedicalFilter().verify(answer, (source,)).ok


def test_doses_are_unique_and_plain_numbers_and_citations_are_not_doses():
    verdict = MedicalFilter().verify("7 mg, 7 mg, 8 mg", ("5 mg",))
    assert verdict.issues[0].count == 2
    assert MedicalFilter().verify("교육 항목 2 [1]", ("교육 자료",)).ok


@pytest.mark.parametrize("evidence", [(), (" \n",)])
def test_absent_evidence_is_not_retryable(evidence):
    verdict = MedicalFilter().verify(GOOD, evidence)
    assert verdict.codes == ("NO_EVIDENCE",) and not verdict.retryable


def test_definitive_diagnosis_remains_visible_without_evidence():
    verdict = MedicalFilter().verify("합성병이 확실", ())
    assert verdict.codes == ("DEFINITIVE_DIAGNOSIS", "NO_EVIDENCE") and not verdict.retryable


def test_empty_answer_and_combined_issues_have_code_only_results():
    assert MedicalFilter().verify(" ", EVIDENCE).codes == ("EMPTY_ANSWER",)
    verdict = MedicalFilter().verify("합성병이 확실. 약물B 7 mg", EVIDENCE)
    assert verdict.codes == ("DEFINITIVE_DIAGNOSIS", "CONTRAINDICATION_DROPPED", "UNSUPPORTED_DOSE")
    assert not verdict.retryable and all(issue.count == 1 for issue in verdict.issues)
    assert "약물" not in repr(verdict) and "합성병" not in repr(verdict)


def test_finalize_adds_both_notices():
    assert MedicalFilter().finalize(GOOD) == GOOD + "\n\n" + DISCLAIMER
    assert "의료 자문이 아닙니다" in DISCLAIMER and "전문의" in DISCLAIMER


def _run(rag, request=REQUEST):
    runner = GuardrailRunner(rag, domain=get_filter("medical"),
                             router=lambda _: RouteDecision(route="research"))
    return asyncio.run(runner.ainvoke(request))


def test_real_graph_finalizes_verified_medical_answer():
    async def rag(_):
        return GuidanceReply(Status.OK, GOOD), EVIDENCE

    result = _run(rag)
    assert result.reply.answer == GOOD + "\n\n" + DISCLAIMER
    assert result.domain == "medical" and result.domain_log == ("SCREEN:PASS", "VERIFY:PASS")


def test_real_graph_blocks_emergency_before_rag():
    async def rag(_):
        pytest.fail("Emergency screening must skip RAG")

    result = _run(rag, {"coreStatement": "합성 사례에서 흉통과 호흡곤란이 발생했습니다."})
    assert result.reply.status == Status.BLOCKED and result.reply.reason_code == "EMERGENCY"
    assert result.path == ("classify", "screen", "finish") and result.loops == 0
    assert result.domain_log == ("SCREEN:BLOCK:EMERGENCY",)


def test_real_graph_does_not_retry_definitive_diagnosis():
    async def rag(_):
        return GuidanceReply(Status.OK, "합성병이 확실"), EVIDENCE

    result = _run(rag)
    assert result.loops == 1 and result.reply.reason_code == "VERIFY_FAILED"
    assert "합성병" not in result.reply.answer and DISCLAIMER not in result.reply.answer


def test_real_graph_retries_correctable_dose_then_finalizes():
    answers = iter([GOOD.replace("5 mg", "7 mg"), GOOD])

    async def rag(_):
        return GuidanceReply(Status.OK, next(answers)), EVIDENCE

    result = _run(rag)
    assert result.loops == 2 and result.reply.answer == GOOD + "\n\n" + DISCLAIMER
    assert result.domain_log == ("SCREEN:PASS", "VERIFY:FAIL:UNSUPPORTED_DOSE", "VERIFY:PASS")


def test_default_graph_behavior_remains_unchanged():
    async def rag(_):
        return GuidanceReply(Status.OK, GOOD), EVIDENCE

    result = asyncio.run(GuardrailRunner(rag).ainvoke(REQUEST))
    assert result.path == ("classify", "rag", "finish") and result.reply.answer == GOOD
