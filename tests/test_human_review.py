"""Offline path tests: real runners, real interrupts and injected InMemorySaver."""
import asyncio
from dataclasses import replace

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from rag_research_agent.core.types import Status
from rag_research_agent.guard.domain_filter import get_filter
from rag_research_agent.rag.guidance import GuidanceReply
from rag_research_agent.rag.guardrail_graph import GuardrailLimits, GuardrailRunner, VERIFY_FAILED_ANSWER
from rag_research_agent.rag.human_review import HumanReviewRunner, ReviewPolicy
from rag_research_agent.rag.research_graph import ResearchConfig, ResearchRunner, keyword_search


QUESTION = "매출 변화의 원인을 분석해 주세요"
EVIDENCE = "매출은 비용 증가 때문에 18% 감소했다."
DRAFT = "매출은 비용 증가 때문에 99% 감소했다."


def run(awaitable):
    return asyncio.run(awaitable)


def guardrail():
    calls = []

    async def generate(request):
        calls.append(request)
        return GuidanceReply(Status.OK, DRAFT), (EVIDENCE,)

    return GuardrailRunner(generate, domain=get_filter("research"),
                           limits=GuardrailLimits(max_verify_rounds=0)), calls


def wrapper(runner, saver=None):
    return HumanReviewRunner(runner, policy=ReviewPolicy(human_review=True),
                             checkpointer=saver if saver is not None else InMemorySaver())


def test_pause_payload_preserves_draft_before_safe_finish():
    runner, calls = guardrail()
    review = wrapper(runner)
    paused = run(review.ainvoke({"coreStatement": QUESTION}, thread_id="review-a1"))
    payload = paused.interrupts[0].value
    assert payload["question"] == QUESTION
    assert payload["draft"] == DRAFT
    assert payload["evidence"] == [EVIDENCE]
    assert "UNSUPPORTED_NUMBER" in payload["failure_codes"]
    assert paused.answer == ""
    assert len(calls) == 1


@pytest.mark.parametrize("action,answer", [("approve", DRAFT), ("edit", EVIDENCE),
                                          ("reject", VERIFY_FAILED_ANSWER)])
def test_three_resume_paths_restore_same_thread_without_regeneration(action, answer):
    runner, calls = guardrail()
    saver = InMemorySaver()
    run(wrapper(runner, saver).ainvoke({"coreStatement": QUESTION}, thread_id="resume-a1"))
    restored = wrapper(runner, saver)
    decision = {"action": action}
    if action == "edit":
        decision["answer"] = answer
    result = run(restored.resume("resume-a1", decision))
    assert result.answer == answer
    assert not result.interrupts
    assert result.event() == {"end_type": "human", "reviewer_action": action}
    assert len(calls) == 1
    if action == "edit":
        assert result.failure_codes == ()
    with pytest.raises(ValueError, match="no pending"):
        run(restored.resume("resume-a1", decision))


def test_failed_edit_rechecks_evidence_and_interrupts_again():
    runner, calls = guardrail()
    review = wrapper(runner)
    run(review.ainvoke({"coreStatement": QUESTION}, thread_id="edit-a1"))
    result = run(review.resume("edit-a1", {"action": "edit", "answer": DRAFT}))
    assert result.interrupts and not result.answer
    assert "UNSUPPORTED_NUMBER" in result.interrupts[0].value["failure_codes"]
    assert run(review.resume("edit-a1", {"action": "reject"})).end_type == "human"
    assert len(calls) == 1


def test_direct_command_resume_uses_real_langgraph():
    runner, _ = guardrail()
    review = wrapper(runner)
    run(review.ainvoke({"coreStatement": QUESTION}, thread_id="command-a1"))
    state = run(review.graph.ainvoke(Command(resume={"action": "approve"}),
                                    config={"configurable": {"thread_id": "command-a1"}}))
    assert state["answer"] == DRAFT and state["end_type"] == "human"


def test_disabled_policy_returns_original_guardrail_result_without_interrupt():
    runner, _ = guardrail()
    review = HumanReviewRunner(runner)
    request = {"coreStatement": QUESTION}
    assert run(review.ainvoke(request)) == run(runner.ainvoke(request))
    assert review.graph is None


@pytest.mark.parametrize("domain,enabled", [("research", False), ("legal", True), ("medical", True)])
def test_domain_policy_defaults_and_override(domain, enabled):
    assert ReviewPolicy(domain).enabled is enabled
    assert ReviewPolicy(domain, not enabled).enabled is not enabled


@pytest.mark.parametrize("decision", [{}, {"action": "other"}, {"action": "edit"},
                                     {"action": "edit", "answer": " "},
                                     {"action": "approve", "answer": "extra"}])
def test_invalid_resume_does_not_consume_pending_review(decision):
    runner, _ = guardrail()
    review = wrapper(runner)
    run(review.ainvoke({"coreStatement": QUESTION}, thread_id="invalid-a1"))
    with pytest.raises(ValueError):
        run(review.resume("invalid-a1", decision))
    assert run(review.resume("invalid-a1", {"action": "reject"})).end_type == "human"


def test_thread_validation_and_isolation():
    runner, _ = guardrail()
    review = wrapper(runner)
    with pytest.raises(ValueError, match="thread_id"):
        run(review.ainvoke({"coreStatement": QUESTION}))
    run(review.ainvoke({"coreStatement": QUESTION}, thread_id="first-a1"))
    run(review.ainvoke({"coreStatement": QUESTION}, thread_id="second-a1"))
    with pytest.raises(ValueError, match="already exists"):
        run(review.ainvoke({"coreStatement": QUESTION}, thread_id="first-a1"))
    with pytest.raises(ValueError, match="no pending"):
        run(review.resume("missing-a1", {"action": "approve"}))
    assert run(review.resume("first-a1", {"action": "approve"})).answer == DRAFT
    assert run(review.resume("second-a1", {"action": "reject"})).answer == VERIFY_FAILED_ANSWER


def test_real_research_failure_and_disabled_result():
    cfg = ResearchConfig(auto_metrics=False, stance_split=False, gap_loop=False, rewrite_loop=False)
    runner = ResearchRunner(keyword_search({"doc-a1": EVIDENCE}), cfg)
    request = {"coreStatement": QUESTION, "checklist": ["거래량"]}
    plain = run(HumanReviewRunner(runner).ainvoke(request))
    assert plain.verify_codes
    review = wrapper(runner)
    paused = run(review.ainvoke(request, thread_id="research-a1"))
    assert paused.interrupts[0].value["draft"] == plain.draft.body()
    assert paused.interrupts[0].value["evidence"] == [c.text for c in plain.claims]
    assert run(review.resume("research-a1", {"action": "approve"})).answer == plain.draft.body()


def test_passing_research_does_not_interrupt():
    cfg = ResearchConfig(auto_metrics=False, stance_split=False, gap_loop=False, rewrite_loop=False)
    runner = ResearchRunner(keyword_search({"doc-a1": EVIDENCE}), cfg)
    result = run(wrapper(runner).ainvoke({"coreStatement": QUESTION}, thread_id="pass-a1"))
    assert result.answer and not result.interrupts and result.end_type == "END"


def test_research_edit_preserves_required_metric_verification():
    cfg = ResearchConfig(auto_metrics=False, stance_split=False, gap_loop=False, rewrite_loop=False)
    runner = ResearchRunner(keyword_search({"doc-a1": EVIDENCE}), cfg)
    review = wrapper(runner)
    run(review.ainvoke({"coreStatement": QUESTION, "checklist": ["거래량"]}, thread_id="metric-a1"))
    edited = run(review.resume("metric-a1", {"action": "edit", "answer": EVIDENCE}))
    assert edited.interrupts and not edited.answer
    assert "GAP:거래량" in edited.failure_codes


def test_enabled_requires_saver_and_nested_review_is_rejected():
    runner, _ = guardrail()
    with pytest.raises(ValueError, match="checkpointer"):
        HumanReviewRunner(runner, policy=ReviewPolicy(human_review=True))
    research = ResearchRunner(keyword_search({}), replace(ResearchConfig(), review_plan=True),
                              checkpointer=InMemorySaver())
    with pytest.raises(ValueError, match="separate integration"):
        wrapper(research)
