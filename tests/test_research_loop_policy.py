"""Offline policy paths through the real compiled graph; no model or network calls."""
from dataclasses import replace

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from rag_research_agent.observe.tracing import serving_config, serving_trace_guard
from rag_research_agent.rag.research_graph import (
    ResearchConfig, ResearchRunner, build_research_graph, est_tokens, keyword_search,
)


TEXT = "매출은 12% 증가했다."
QUESTION = "매출 분석"
CORPUS = {"doc-a1": TEXT}
CFG = ResearchConfig(stance_split=False, auto_metrics=False)


def run(cfg=CFG, *, verdicts=None, checklist=("매출",), checkpoint=False, corpus=CORPUS,
        reopen_gap=False):
    """Script only verifier decisions, retaining real retrieval/extraction/writing."""
    plugins = {}
    if verdicts is not None:
        decisions = iter(verdicts)

        def verifier(*args, **kwargs):
            return next(decisions)

        plugins["verifier"] = verifier
    with serving_trace_guard():
        saver = InMemorySaver() if checkpoint or reopen_gap else None
        graph = build_research_graph(keyword_search(corpus), cfg,
                                     checkpointer=saver,
                                     fallback_on_error=False, **plugins)
        config = {**serving_config(), "recursion_limit": 100}
        if saver is not None:
            config["configurable"] = {"thread_id": "policy-a1"}
        graph_input = {"question": QUESTION, "checklist": checklist}
        if reopen_gap:
            # Seed a caller-edited checkpoint through the real graph and saver.
            # Normal coverage spends its gap rounds before write, so explicitly
            # reopen one metric to exercise both available verifier edges.
            bootstrap = build_research_graph(keyword_search(corpus), cfg, checkpointer=saver)
            bootstrap.invoke(graph_input, config=config)
            graph.update_state(config, {"gaps": ("매출",), "gap_rounds": {}}, as_node="write")
            graph_input = None
        path = []
        state = {}
        for mode, payload in graph.stream(graph_input,
                                          config=config, stream_mode=["updates", "values"]):
            if mode == "updates":
                path.extend(payload)
            else:
                state = payload
        return state, tuple(path)


def tokens(state):
    return sum(t for _, _, t in state["cost"])


def test_default_policy_preserves_single_pass_report_path_and_cost():
    result = ResearchRunner(keyword_search(CORPUS), CFG).run(QUESTION, ("매출",))
    assert result.path == ("plan", "retrieve", "refine", "extract", "compare", "coverage", "write", "verify")
    assert result.report == TEXT + " [doc-a1#0]"
    assert result.verify_codes == () and result.stopped == ""
    assert result.cost == (
        ("plan", "model_in", est_tokens(QUESTION)), ("retrieve", "search", 0),
        ("extract", "model_in", est_tokens(TEXT)),
        ("write", "model_in", est_tokens(QUESTION + TEXT)),
        ("write", "model_out", est_tokens(TEXT)),
    )
    explicit = replace(CFG, rewrite_codes=None, gap_first=True, per_node_token_cap=None,
                       stop_if_no_progress=False)
    assert result == ResearchRunner(keyword_search(CORPUS), explicit).run(QUESTION, ("매출",))


@pytest.mark.parametrize("code", ["LOW_DENSITY", "NO_EVIDENCE", "CUSTOM_STYLE"])
def test_default_still_rewrites_every_non_gap_code_until_existing_limit(code):
    state, path = run(verdicts=[(code,)] * 3)
    assert path.count("rewrite") == CFG.max_rewrites
    assert path.count("verify") == 3
    assert not state["stopped"]


@pytest.mark.parametrize("allowed", [frozenset(), frozenset({"CAUSAL_LOSS"})])
def test_rewrite_code_selection_changes_loops_and_estimated_cost(allowed):
    baseline, original = run(verdicts=[("LOW_DENSITY",)] * 3)
    selected, path = run(replace(CFG, rewrite_codes=allowed), verdicts=[("LOW_DENSITY",)])
    assert original.count("rewrite") == 2 and "rewrite" not in path
    assert tokens(selected) < tokens(baseline)
    assert selected["verify_codes"] == ("LOW_DENSITY",)


def test_selected_code_rewrites_with_all_verifier_feedback():
    state, path = run(replace(CFG, rewrite_codes=frozenset({"LOW_DENSITY"})),
                      verdicts=[("LOW_DENSITY", "CUSTOM_STYLE"), ()])
    assert path.count("rewrite") == 1
    assert state["feedback"] == ("LOW_DENSITY", "CUSTOM_STYLE")
    assert state["verify_codes"] == ()


def test_gap_code_cannot_be_redirected_to_rewrite_by_code_selection():
    _, path = run(replace(CFG, gap_loop=False, rewrite_codes=frozenset({"GAP:매출"})),
                  verdicts=[("GAP:매출",)])
    assert "rewrite" not in path and "retrieve_gap" not in path


def test_gap_priority_changes_route_loop_count_and_cost():
    # A source-covered metric keeps initial coverage from consuming the gap budget.
    # The verifier then requests the same metric and a style correction together.
    verdicts = [("GAP:매출", "LOW_DENSITY"), ()]
    cfg = replace(CFG, k=1)
    corpus = {**CORPUS, "doc-b1": "매출은 15% 증가했다."}
    first, gap_path = run(cfg, verdicts=verdicts, corpus=corpus, reopen_gap=True)
    second, rewrite_path = run(replace(cfg, gap_first=False), verdicts=verdicts,
                               corpus=corpus, reopen_gap=True)
    assert gap_path[gap_path.index("verify") + 1] == "retrieve_gap"
    assert rewrite_path[rewrite_path.index("verify") + 1] == "rewrite"
    assert first["gap_rounds"] == {"매출": 1} and first["rewrites"] == 0
    assert second["gap_rounds"] == {} and second["rewrites"] == 1
    assert len(first["claims"]) > len(second["claims"])
    assert tokens(first) > tokens(second)


def test_rewrite_first_falls_back_to_gap_when_rewrite_unavailable():
    state, path = run(replace(CFG, gap_first=False, rewrite_codes=frozenset()),
                      verdicts=[("GAP:매출", "LOW_DENSITY"), ()], reopen_gap=True)
    assert path[path.index("verify") + 1] == "retrieve_gap"
    assert state["gap_rounds"] == {"매출": 1}


@pytest.mark.parametrize("checkpoint", [False, True])
@pytest.mark.parametrize("parallel", [False, True])
def test_node_cap_stops_after_plan_before_any_retrieval(checkpoint, parallel):
    cap = est_tokens(QUESTION)
    state, path = run(replace(CFG, per_node_token_cap=cap, parallel_branches=parallel), checkpoint=checkpoint)
    assert path == ("plan",)
    assert state["stopped"] == "PER_NODE_TOKEN_CAP"
    assert tokens(state) == cap


@pytest.mark.parametrize("checkpoint", [False, True])
def test_node_cap_combines_writer_input_output_without_clipping(checkpoint):
    baseline, _ = run(checkpoint=checkpoint)
    write_cost = sum(t for node, _, t in baseline["cost"] if node == "write")
    cap = write_cost - 1
    assert all(t < cap for node, _, t in baseline["cost"] if node == "write")
    limited, path = run(replace(CFG, per_node_token_cap=cap), checkpoint=checkpoint)
    assert path[-1] == "write" and "verify" not in path
    assert limited["stopped"] == "PER_NODE_TOKEN_CAP"
    assert limited["cost"] == baseline["cost"]  # spent estimates are never clamped
    # A cap can save later loop cost while preserving the work already performed.
    looping, _ = run(verdicts=[("LOW_DENSITY",)] * 3)
    assert tokens(limited) < tokens(looping)


def test_node_cap_stops_at_extract_and_large_cap_preserves_result():
    state, path = run(replace(CFG, per_node_token_cap=est_tokens(TEXT)))
    assert path[-1] == "extract" and state["stopped"] == "PER_NODE_TOKEN_CAP"
    assert run(replace(CFG, per_node_token_cap=1000)) == run()


@pytest.mark.parametrize("cap", [0, -1, True, 1.5])
def test_invalid_node_caps_fail_before_execution(cap):
    with pytest.raises(ValueError, match="per_node_token_cap"):
        build_research_graph(keyword_search(CORPUS), replace(CFG, per_node_token_cap=cap))


@pytest.mark.parametrize("checkpoint", [False, True])
def test_repeated_code_stops_at_second_verification_and_saves_tokens(checkpoint):
    baseline, original = run(verdicts=[("LOW_DENSITY",)] * 3, checkpoint=checkpoint)
    state, path = run(replace(CFG, stop_if_no_progress=True),
                      verdicts=[("LOW_DENSITY",)] * 2, checkpoint=checkpoint)
    assert original.count("rewrite") == 2 and path.count("rewrite") == 1
    assert path.count("verify") == 2 and state["stopped"] == "NO_PROGRESS"
    assert "STOP:NO_PROGRESS" in state["log"] and tokens(state) < tokens(baseline)


@pytest.mark.parametrize("verdicts,stopped", [
    ([("LOW_DENSITY", "CAUSAL_LOSS"), ("ONE_SIDED", "LOW_DENSITY")], "NO_PROGRESS"),
    ([("LOW_DENSITY",), ("CAUSAL_LOSS",), ()], ""),
    ([("LOW_DENSITY",), ()], ""),
])
def test_no_progress_tracks_individual_codes_and_pass_does_not_stop(verdicts, stopped):
    state, path = run(replace(CFG, stop_if_no_progress=True), verdicts=verdicts)
    assert state["stopped"] == stopped
    assert path.count("verify") == len(verdicts)


def test_repeated_gap_verdict_also_stops():
    state, path = run(replace(CFG, stop_if_no_progress=True), verdicts=[("GAP:매출",)] * 2,
                      reopen_gap=True)
    assert state["stopped"] == "NO_PROGRESS" and path.count("retrieve_gap") == 1


def test_runner_marks_cap_interrupted_draft_as_unverified():
    result = ResearchRunner(keyword_search(CORPUS), replace(CFG, per_node_token_cap=1)).run(QUESTION)
    assert result.stopped == "PER_NODE_TOKEN_CAP"
    assert result.path == ("plan",) and "연구 중단: PER_NODE_TOKEN_CAP" in result.report
