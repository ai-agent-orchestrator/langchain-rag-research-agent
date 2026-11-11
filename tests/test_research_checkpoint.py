"""Offline path tests using the real research graph and LangGraph MemorySaver."""
from dataclasses import replace
import json

import pytest
from langgraph.checkpoint.memory import MemorySaver

from rag_research_agent.core.research import Claim, Draft, Metric, Relation, ReportSentence, ResearchPlan, SourceRef
from rag_research_agent.rag import research_graph
from rag_research_agent.rag.research_graph import ResearchConfig, ResearchRunner, keyword_search


CORPUS = {"doc-a1": "매출은 18% 증가했다. 거래량은 12% 감소했다."}
CONFIG = ResearchConfig(auto_metrics=False, stance_split=False, gap_loop=False, rewrite_loop=False)


def test_checkpoint_codec_restores_tuple_contract_after_json_round_trip():
    state = {
        "plan": ResearchPlan(("매출",), (("매출", "review"),)),
        "checklist": ("매출",), "gaps": ("거래량",),
        "feedback": ("GAP:거래량",), "verify_codes": ("GAP:거래량",),
        "cost": [("plan", "model_in", 7), ("retrieve", "search", 0)],
        "draft": Draft((ReportSentence("매출은 18% 증가했다.", ("claim-a1",)),)),
    }
    records = research_graph._checkpoint_state(state)
    decoded = json.loads(json.dumps(records))
    restored = research_graph._checkpoint_state(decoded, restore=True)
    assert restored == state
    assert all(isinstance(item, tuple) for item in restored["cost"])
    assert research_graph._checkpoint_state(restored) == records


@pytest.mark.parametrize("parallel", [False, True])
def test_review_resumes_without_replanning_or_duplicate_search(monkeypatch, parallel):
    search_calls, plan_calls = [], []
    search = keyword_search(CORPUS)
    plan = research_graph.plan_rule

    def counted_search(query, k):
        search_calls.append((query, k))
        return search(query, k)

    def counted_plan(*args):
        plan_calls.append(args)
        return plan(*args)

    monkeypatch.setattr(research_graph, "plan_rule", counted_plan)
    cfg = replace(CONFIG, review_plan=True, parallel_branches=parallel)
    saver = MemorySaver()
    runner = ResearchRunner(counted_search, cfg, checkpointer=saver)
    paused = runner.run("매출 거래량 분석", ("매출",), thread_id="review-a1")
    assert paused.path == ("plan",)
    assert paused.plan.required_metrics == ("매출",)
    assert paused.interrupts[0].value == {"required_metrics": ["매출"]}
    assert not paused.report and not search_calls
    assert len(plan_calls) == 1

    # A new runner with the same saver must use saved state, not in-process accumulation.
    resumed = ResearchRunner(counted_search, cfg, checkpointer=saver).resume(
        "review-a1", required_metrics=[" 거래량 ", "거래량"])
    assert len(plan_calls) == 1
    assert len(search_calls) == 1
    assert "plan" not in resumed.path and "review_plan" in resumed.path
    assert resumed.plan.required_metrics == ("거래량",)
    assert resumed.plan.origin == (("거래량", "review"),)
    assert any(m.name == "거래량" for m in resumed.metrics)
    assert not resumed.interrupts and resumed.report
    assert sum(code.startswith("PLAN:") for code in resumed.log) == 1
    assert sum(node == "plan" for node, _, _ in resumed.cost) == 1


def test_default_without_checkpointer_is_unchanged():
    plain = ResearchRunner(keyword_search(CORPUS), CONFIG).run("매출 분석", ("매출",))
    saved = ResearchRunner(keyword_search(CORPUS), CONFIG, checkpointer=MemorySaver()).run(
        "매출 분석", ("매출",), thread_id="default-a1")
    assert plain == saved
    assert ResearchConfig().review_plan is False
    assert not plain.interrupts and "review_plan" not in plain.path


def test_review_requires_checkpointer():
    with pytest.raises(ValueError, match="checkpointer"):
        ResearchRunner(keyword_search(CORPUS), replace(CONFIG, review_plan=True))


@pytest.mark.parametrize("thread_id", [None, "", " "])
def test_checkpointer_requires_nonblank_thread(thread_id):
    runner = ResearchRunner(keyword_search(CORPUS), CONFIG, checkpointer=MemorySaver())
    with pytest.raises(ValueError, match="thread_id"):
        runner.run("매출 분석", thread_id=thread_id)


def test_thread_without_checkpointer_is_rejected():
    with pytest.raises(ValueError, match="checkpointer"):
        ResearchRunner(keyword_search(CORPUS), CONFIG).run("매출 분석", thread_id="unused-a1")


@pytest.mark.parametrize("metrics", ["매출", [""], [" "], [None], [1], None])
def test_invalid_edit_does_not_consume_review(metrics):
    runner = ResearchRunner(keyword_search(CORPUS), replace(CONFIG, review_plan=True),
                            checkpointer=MemorySaver())
    runner.run("매출 분석", thread_id="invalid-a1")
    with pytest.raises(ValueError, match="required_metrics"):
        runner.resume("invalid-a1", required_metrics=metrics)
    assert runner.resume("invalid-a1", required_metrics=["매출"]).plan.required_metrics == ("매출",)


def test_threads_are_isolated_and_completed_review_cannot_resume():
    runner = ResearchRunner(keyword_search(CORPUS), replace(CONFIG, review_plan=True),
                            checkpointer=MemorySaver())
    runner.run("매출 분석", thread_id="first-a1")
    runner.run("거래량 분석", thread_id="second-a1")
    with pytest.raises(ValueError, match="no pending"):
        runner.resume("unknown-a1", required_metrics=[])
    with pytest.raises(ValueError, match="already exists"):
        runner.run("새 질문", thread_id="first-a1")
    first = runner.resume("first-a1", required_metrics=["매출"])
    second = runner.resume("second-a1", required_metrics=[])
    assert first.plan.required_metrics == ("매출",)
    assert second.plan.required_metrics == ()
    assert first.plan.perspectives == second.plan.perspectives == ("base", "pro", "con")
    with pytest.raises(ValueError, match="no pending"):
        runner.resume("first-a1", required_metrics=["거래량"])


def test_resume_without_review_is_rejected():
    runner = ResearchRunner(keyword_search(CORPUS), CONFIG, checkpointer=MemorySaver())
    runner.run("매출 분석", thread_id="no-review-a1")
    with pytest.raises(ValueError, match="plan review"):
        runner.resume("no-review-a1", required_metrics=[])


@pytest.mark.parametrize("parallel", [False, True])
def test_saved_records_restore_real_types_through_gap_loops(parallel):
    corpus = {"doc-a1": "매출은 비용 증가 때문에 18% 감소했다. 다만 국내 대상에 한정된다."}
    cfg = replace(CONFIG, review_plan=True, gap_loop=True, parallel_branches=parallel)
    saver = MemorySaver()
    original_serializer = saver.serde
    runner = ResearchRunner(keyword_search(corpus), cfg, checkpointer=saver)
    runner.run("매출 분석", ("매출",), thread_id="records-a1")
    config = {"configurable": {"thread_id": "records-a1"}}
    paused_state = runner.graph.get_state(config).values
    assert isinstance(paused_state["plan"], dict)
    assert research_graph._checkpoint_state(paused_state, restore=True)["plan"] == ResearchPlan(
        ("매출",), (("매출", "checklist"),))

    restored_runner = ResearchRunner(keyword_search(corpus), cfg, checkpointer=saver)
    result = restored_runner.resume("records-a1", required_metrics=["매출", "거래량"])
    assert isinstance(result.plan, ResearchPlan)
    assert isinstance(result.draft, Draft)
    assert result.claims and all(isinstance(item, Claim) for item in result.claims)
    assert result.metrics and all(isinstance(item, Metric) for item in result.metrics)
    assert result.sources and all(isinstance(item, SourceRef) for item in result.sources)
    assert "retrieve_gap" in result.path
    saved_state = restored_runner.graph.get_state(config).values
    assert saved_state["relations"]
    assert all(isinstance(item, dict) for field in ("sources", "claims", "metrics", "relations")
               for item in saved_state[field])
    restored_state = research_graph._checkpoint_state(saved_state, restore=True)
    assert all(isinstance(item, Relation) for item in restored_state["relations"])
    assert result.draft.sentences[:len(restored_state["draft"].sentences)] == restored_state["draft"].sentences
    assert saver.serde is original_serializer
