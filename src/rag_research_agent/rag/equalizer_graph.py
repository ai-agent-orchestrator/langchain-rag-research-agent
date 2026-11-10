"""Compiled Equalizer stages behind an invocation-wide serving trace guard."""
from __future__ import annotations

MATURITY = "incubating"

from langchain_core.runnables import Runnable
from langgraph.graph import StateGraph, START, END
from rag_research_agent.rag.brief import Parts
from rag_research_agent.rag import stages
from rag_research_agent.observe.local_log import append_trace
from rag_research_agent.observe.tracing import serving_trace_guard


class ServingGraph(Runnable):
    """Runnable subgraph boundary: the guard starts before LangGraph tracing starts."""
    def __init__(self, compiled, log_path):
        self.compiled, self.log_path = compiled, log_path

    def _config(self, config):
        return {**(config or {}), "callbacks": [], "tags": [], "metadata": {}, "run_name": "equalizer"}

    def _record(self, state):
        if self.log_path is not None:
            append_trace(state, self.log_path)
        return state

    def invoke(self, input, config=None, **kwargs):
        with serving_trace_guard():
            return self._record(self.compiled.invoke(input, config=self._config(config), **kwargs))

    async def ainvoke(self, input, config=None, **kwargs):
        with serving_trace_guard():
            return self._record(await self.compiled.ainvoke(input, config=self._config(config), **kwargs))

    def get_graph(self, config=None, **kwargs):
        return self.compiled.get_graph(config=config, **kwargs)


def build_graph(parts=None, profile=None, *, log_path=".runs/trace.jsonl"):
    preset = None
    if profile is not None:
        from rag_research_agent.rag.profile import Equalizer
        eq = profile if isinstance(profile, Equalizer) else Equalizer.from_profile(profile)
        parts = parts or eq.parts()
        preset = eq.profile.name
    base = parts or Parts()
    graph = StateGraph(dict)
    def prepare_node(state):
        default_preset = None if profile is not None and state.get("knobs") is not None else preset
        return stages.prepare(base, state["raw_draft"], state.get("task"), state.get("knobs"),
                              state.get("preset", default_preset), state.get("budget", 600), state.get("focus"), state.get("packs"))
    graph.add_node("prepare", prepare_node)
    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "guard_input")
    for index, function in enumerate(stages.STAGES):
        name = function.__name__
        def node(state, function=function):
            return function(state, state["parts"])
        graph.add_node(name, node)
        following = stages.STAGES[index + 1].__name__ if index + 1 < len(stages.STAGES) else END
        graph.add_conditional_edges(name, lambda state, following=following: END if state.get("_finished") else following,
                                    {END: END, following: following})
    return ServingGraph(graph.compile(), log_path)
