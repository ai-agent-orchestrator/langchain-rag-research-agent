"""Offline plugin path tests through the real compiled research graph."""
from dataclasses import replace

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from rag_research_agent.core.research import Claim, Draft, ReportSentence, ResearchPlan
from rag_research_agent.guard.research_filter import verify_report
from rag_research_agent.observe.tracing import serving_config, serving_trace_guard
from rag_research_agent.rag.research_graph import (
    ResearchConfig, build_research_graph, extract_rule, keyword_search, plan_rule,
    refine_rule, write_rule,
)


CFG = ResearchConfig(stance_split=False, gap_loop=False, rewrite_loop=False)
TEXT = "매출은 12% 증가했다. 다만 일부 지역은 제외된다."
CORPUS = {"doc-a1": TEXT}
NODES = ("planner", "extractor", "writer", "verifier", "refiner")


def run(*, cfg=CFG, checkpointer=None, **plugins):
    with serving_trace_guard():
        graph = build_research_graph(keyword_search(CORPUS), cfg,
                                     checkpointer=checkpointer, **plugins)
        config = {**serving_config(), "recursion_limit": 60}
        if checkpointer is not None:
            config["configurable"] = {"thread_id": "plugin-a1"}
        return graph.invoke({"question": "매출 분석", "checklist": ("매출",)}, config=config)


def test_planner_replacement_changes_plan():
    def planner(question, checklist, cfg):
        assert question == "매출 분석" and checklist == ("매출",)
        return ResearchPlan(("비용",), (("비용", "plugin"),))

    assert run(planner=planner)["plan"].required_metrics == ("비용",)


def test_extractor_replacement_changes_claims_and_keeps_span_guard():
    def extractor(sources, plan, known):
        assert sources[0].source_id == "doc-a1" and not known
        text = "다만 일부 지역은 제외된다."
        good = Claim("claim-a1", "doc-a1", TEXT.index(text), len(TEXT), text,
                     "neutral", "constraint")
        bad = replace(good, claim_id="claim-b1", text="지어낸 문장입니다.")
        return [good, bad], [], []

    state = run(extractor=extractor)
    assert [c.claim_id for c in state["claims"]] == ["claim-a1"]
    assert "EXTRACT:claims=1,bad_span=1" in state["log"]


def test_writer_replacement_changes_draft_and_receives_feedback_contract():
    def writer(plan, claims, feedback, cfg, no_con):
        assert plan.required_metrics == ("매출",) and claims
        assert feedback == () and not no_con
        return Draft((ReportSentence("작성기 교체 경로", note=True),))

    assert run(writer=writer)["draft"].sentences == (ReportSentence("작성기 교체 경로", note=True),)


def test_verifier_replacement_changes_verdict():
    def verifier(draft, plan, claims, metrics, *, expect_balance):
        assert draft.sentences and claims and metrics and not expect_balance
        return ("PLUGIN_REVIEW",)

    assert run(verifier=verifier)["verify_codes"] == ("PLUGIN_REVIEW",)


def test_refiner_replacement_changes_extraction_input():
    def refiner(sources, cfg):
        assert sources[0].text == TEXT
        return [], ["PLUGIN_REFINE"]

    state = run(refiner=refiner)
    assert state["claims"] == [] and "PLUGIN_REFINE" in state["log"]
    assert state["sources"][0].text == TEXT


@pytest.mark.parametrize("name", NODES)
def test_plugin_exception_falls_back_to_rules_with_code_only(name):
    def broken(*args, **kwargs):
        raise RuntimeError("PRIVATE_PLUGIN_ERROR")

    baseline = run()
    state = run(**{name: broken})
    # Compare every output field, including costs and reducer state, except the extra code.
    assert state["log"].count("PLUGIN_FALLBACK:" + name.upper()) == 1
    assert "PRIVATE_PLUGIN_ERROR" not in repr(state)
    assert {key: value for key, value in state.items() if key != "log"} == {
        key: value for key, value in baseline.items() if key != "log"}
    assert [code for code in state["log"] if not code.startswith("PLUGIN_FALLBACK:")] == baseline["log"]


@pytest.mark.parametrize("name", NODES)
def test_fallback_can_be_disabled(name):
    def broken(*args, **kwargs):
        raise RuntimeError("PLUGIN_ERROR")

    with pytest.raises(RuntimeError, match="PLUGIN_ERROR"):
        run(fallback_on_error=False, **{name: broken})


@pytest.mark.parametrize("cfg", [CFG, ResearchConfig(), replace(CFG, drop_generic=True),
                                  replace(CFG, parallel_branches=True)])
def test_explicit_rules_match_default_state(cfg):
    assert run(cfg=cfg, planner=plan_rule, extractor=extract_rule, writer=write_rule,
               verifier=verify_report, refiner=refine_rule) == run(cfg=cfg)


def test_explicit_plugins_take_precedence_over_model_modes():
    state = run(cfg=replace(CFG, planner="llm", extractor="llm"),
                planner=plan_rule, extractor=extract_rule)
    assert state == run()


def test_plugins_work_with_real_checkpoint_serialization():
    state = run(checkpointer=InMemorySaver(), planner=plan_rule, writer=write_rule,
                extractor=extract_rule, verifier=verify_report, refiner=refine_rule)
    assert state["draft"]["sentences"]
    assert tuple(state["plan"]["required_metrics"]) == ("매출",)


def test_verifier_plugin_preserves_rewrite_routing():
    feedback_seen = []

    def writer(plan, claims, feedback, cfg, no_con):
        feedback_seen.append(feedback)
        return write_rule(plan, claims, feedback, cfg, no_con)

    def verifier(draft, plan, claims, metrics, *, expect_balance):
        return ("LOW_DENSITY",) if len(feedback_seen) == 1 else ()

    state = run(cfg=replace(CFG, rewrite_loop=True), writer=writer, verifier=verifier)
    assert feedback_seen == [(), ("LOW_DENSITY",)]
    assert state["rewrites"] == 1 and state["verify_codes"] == ()
