"""Offline path tests through the real research graph; no external models."""
from dataclasses import replace
from typing import get_args

import pytest
from langgraph.checkpoint.memory import MemorySaver

from rag_research_agent.rag.research_graph import (
    EndType, ResearchConfig, ResearchRunner, keyword_search,
)
from rag_research_agent.rag.run_trace import event_from_result


CONFIG = ResearchConfig(auto_metrics=False, stance_split=False)
CORPUS = {"doc-a1": "매출은 18% 증가했다."}


def run(cfg=CONFIG, checklist=(), corpus=CORPUS):
    return ResearchRunner(keyword_search(corpus), cfg).run("매출 분석", checklist)


def assert_event(result, expected, *, rewrite, gap, verify):
    event = event_from_result(result, "research", {})
    assert result.end_type == event.end_type == expected
    assert dict(event.loops) == {"rewrite": rewrite, "gap": gap, "verify": verify}
    assert event.path == result.path


def test_verified_end():
    result = run(checklist=("매출",))
    assert not result.verify_codes and result.stopped == ""
    assert_event(result, "END", rewrite=0, gap=0, verify=0)


def test_gap_exhaustion_gives_up_with_reason():
    result = run(replace(CONFIG, max_gap_rounds=1, rewrite_loop=False), ("거래량",))
    assert "GAP:거래량" in result.verify_codes
    assert "검수 미통과 항목:" in result.report
    assert result.stopped == ""  # legacy field is preserved
    assert_event(result, "give_up", rewrite=0, gap=1, verify=0)


def test_rewrite_exhaustion_gives_up_even_without_a_draft():
    result = run(replace(CONFIG, gap_loop=False, max_rewrites=1), corpus={})
    assert result.verify_codes
    assert "검수 미통과 항목:" in result.report
    assert all(sentence.note for sentence in result.draft.sentences)
    assert_event(result, "give_up", rewrite=1, gap=0, verify=1)


@pytest.mark.parametrize("cfg,checklist", [
    (replace(CONFIG, per_node_token_cap=1), ()),
    (replace(CONFIG, max_shadow_tokens=1), ("거래량",)),
])
def test_token_cutoff(cfg, checklist):
    result = run(cfg, checklist)
    assert result.shadow_tokens >= 1
    assert_event(result, "cutoff", rewrite=0, gap=0, verify=0)


def test_event_needs_no_budget_metadata():
    result = run(replace(CONFIG, max_shadow_tokens=1), ("거래량",))
    assert result.end_type == "cutoff"
    assert event_from_result(result, "research", {}).end_type == "cutoff"


def test_human_value_reserved_and_existing_review_compatible():
    assert get_args(EndType) == ("END", "give_up", "cutoff", "human")
    runner = ResearchRunner(keyword_search(CORPUS), replace(CONFIG, review_plan=True),
                            checkpointer=MemorySaver())
    paused = runner.run("매출 분석", ("매출",), thread_id="review-a1")
    assert paused.interrupts and paused.path == ("plan",)
    assert not paused.report and not paused.stopped
    # R46 must extend core.run_events before publishing human events.
    assert_event(paused, "give_up", rewrite=0, gap=0, verify=0)
    resumed = runner.resume("review-a1", required_metrics=["매출"])
    assert not resumed.interrupts
    assert_event(resumed, "END", rewrite=0, gap=0, verify=0)


def test_loop_limit_is_give_up_rather_than_cost_cutoff():
    result = replace(run(), stopped="LOOP_LIMIT")
    assert_event(result, "give_up", rewrite=0, gap=0, verify=0)
