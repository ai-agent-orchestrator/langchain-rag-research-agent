"""Opt-in, checkpointed follow-up research over already-masked local evidence.

The caller owns the saver, corpus scope and thread ID. A thread denotes one
research topic; changing corpus, permissions or topic requires a new thread.
Limits apply to the latest checkpoint, not to the saver's historical versions.
"""
from __future__ import annotations

MATURITY = "incubating"

from typing import TypedDict

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from rag_research_agent.core.research import span_matches
from rag_research_agent.observe.tracing import serving_config, serving_trace_guard
from rag_research_agent.rag.research_graph import (
    ResearchConfig, ResearchResult, ResearchRunner, SearchFn, _checkpoint_state,
    build_research_graph, coverage_rule, est_tokens, plan_rule,
)


class SessionState(TypedDict, total=False):
    memory: dict
    messages: list[dict]
    events: list[dict]


class _TurnRunner(ResearchRunner):
    """Use the existing result/serialization adapter with graph plugins enabled."""

    def __init__(self, search, cfg, **plugins):
        from langgraph.checkpoint.memory import MemorySaver

        self.cfg, self.search = cfg, search
        self.checkpointer = MemorySaver()
        self.graph = build_research_graph(search, cfg, checkpointer=self.checkpointer, **plugins)


def _trim(state: dict, limit: int) -> dict:
    sources = state.get("sources", [])[-limit:]
    by_id = {s.source_id: s for s in sources}
    claims = [c for c in state.get("claims", []) if span_matches(c, by_id)][-limit:]
    ids = {c.claim_id for c in claims}
    return {
        "sources": sources, "claims": claims,
        "metrics": [m for m in state.get("metrics", [])
                    if m.claim_id in ids and m.source_id in by_id][-limit:],
        "relations": [r for r in state.get("relations", [])
                      if r.src in ids and r.dst in ids][-limit:],
    }


class ResearchSession:
    """Use ``run(question, search=...)`` to continue the same masked topic.

    SearchFn can be the real Chroma adapter. Model/plugin arguments are passed
    to the existing graph builder; no model or store is loaded by this class.
    Completed turns only are persisted. Plan-review interrupts remain the
    ResearchRunner API's responsibility and are rejected here explicitly.
    """

    def __init__(self, thread_id: str, checkpointer: BaseCheckpointSaver | None,
                 *, max_items: int = 50):
        if checkpointer is None:
            raise ValueError("ResearchSession requires a checkpointer")
        if not isinstance(thread_id, str) or not thread_id.strip():
            raise ValueError("ResearchSession requires a nonblank thread_id")
        if isinstance(max_items, bool) or not isinstance(max_items, int) or max_items < 1:
            raise ValueError("max_items must be a positive integer")
        self.thread_id = thread_id
        self.checkpointer = checkpointer
        self.max_items = max_items
        self.last_event: dict | None = None

    def run(self, question: str, checklist: tuple[str, ...] = (), *, search: SearchFn,
            cfg: ResearchConfig = ResearchConfig(), **plugins) -> ResearchResult:
        if cfg.review_plan:
            raise ValueError("session plan review requires follow-up integration; use ResearchRunner")
        if "checkpointer" in plugins:
            raise ValueError("the session owns its checkpointer")
        if cfg.planner == "llm" and plugins.get("planner") is None:
            from rag_research_agent.rag.research_llm import llm_planner

            if plugins.get("planner_model") is None:
                raise ValueError("llm planning requires planner_model")
            plugins = {**plugins, "planner": llm_planner(plugins["planner_model"], plugins.get("masker"))}
        results: list[ResearchResult] = []

        def turn(saved: SessionState):
            memory = _trim(_checkpoint_state(saved.get("memory", {}), restore=True), self.max_items)
            # Only span-validated extracted evidence may be reused. Retrieved but
            # rejected documents must not satisfy coverage or suppress a search.
            supported = {c.source_id for c in memory["claims"]}
            reused = [s for s in memory["sources"] if s.source_id in supported]
            memory["sources"] = reused
            gaps: tuple[str, ...] | None = None
            requested_plan = plugins.get("planner") or plan_rule

            def planner(q, items, config):
                nonlocal gaps
                plan = requested_plan(q, items, config)
                if reused and plan.required_metrics:
                    gaps = coverage_rule(plan, memory["claims"], memory["metrics"])
                return plan

            def gap_search(query, k):
                if gaps is None:
                    return search(query, k)
                if not gaps:
                    return []
                # Keep the existing stance branches and retry budgets, but never
                # put already-covered metrics from the question into retrieval.
                if query.startswith(question):
                    query = " ".join(gaps) + query[len(question):]
                else:
                    query = query.replace(question, "").strip()
                return search(query, k)

            options = {**plugins, "planner": planner}
            # A private, turn-local real saver lets ResearchRunner assemble both
            # seeded and new reducer state without carrying prior cost/budgets.
            runner = _TurnRunner(gap_search, cfg, **options)
            seed = {**memory, "question": question, "checklist": tuple(checklist)}
            result = runner._execute(_checkpoint_state(seed), runner._config("turn"))
            results.append(result)
            snapshot = _checkpoint_state(runner.graph.get_state(runner._config("turn")).values,
                                         restore=True)
            event = {"thread_id": self.thread_id, "reused_sources": len(reused),
                     "saved_shadow_tokens": est_tokens(" ".join(s.text for s in reused)),
                     "estimated": True, "end_type": result.end_type,
                     "shadow_tokens": result.shadow_tokens, "path": list(result.path)}
            self.last_event = event
            messages = saved.get("messages", []) + [
                {"role": "user", "content": question},
                {"role": "assistant", "content": result.report},
            ]
            return {"memory": _checkpoint_state(_trim(snapshot, self.max_items)),
                    "messages": messages[-self.max_items:],
                    "events": (saved.get("events", []) + [event])[-self.max_items:]}

        graph = StateGraph(SessionState)
        graph.add_node("research", turn)
        graph.add_edge(START, "research")
        graph.add_edge("research", END)
        compiled = graph.compile(checkpointer=self.checkpointer)
        config = {**serving_config(), "configurable": {"thread_id": self.thread_id}}
        with serving_trace_guard():
            compiled.invoke({}, config=config)
        return results[0]
