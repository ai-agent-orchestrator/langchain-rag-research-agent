"""Retrieve/grade/rewrite loop with a hard two-retry cap and shared Equalizer stages."""
from __future__ import annotations

MATURITY = "incubating"

import math
from langgraph.graph import StateGraph, START, END

from rag_research_agent.core.types import Status
from rag_research_agent.rag.equalizer_graph import ServingGraph
from rag_research_agent.rag.profile import Equalizer
from rag_research_agent.rag.query_rewrite import rewrite_queries
from rag_research_agent.rag import stages


def _rrf(rankings, k):
    fused, raw, chunks = {}, {}, {}
    for hits in rankings:
        seen = set()
        for rank, (chunk, score, _) in enumerate(hits, 1):
            cid = chunk.chunk_id
            if cid in seen:
                continue
            seen.add(cid)
            if not math.isfinite(float(score)):
                raise ValueError("non-finite retrieval score")
            chunks[cid] = chunk
            raw[cid] = max(raw.get(cid, float("-inf")), score)
            fused[cid] = fused.get(cid, 0) + 1 / (60 + rank)
    order = sorted(fused, key=lambda cid: (-fused[cid], -raw[cid], cid))[:k]
    return [(chunks[cid], raw[cid], rank) for rank, cid in enumerate(order, 1)], {cid: fused[cid] for cid in order}


def build_graph(library, profile="research", tau=None, k=3, max_retries=2, parts=None, mode="vector", *, log_path=None):
    if max_retries not in (0, 1, 2) or k < 1:
        raise ValueError("max_retries must be 0..2 and k must be positive")
    eq = Equalizer.from_profile(profile)
    base = parts or eq.parts()
    tau = eq.config.mapper.map(eq.profile.preset.knobs).threshold if tau is None else float(tau)
    if not math.isfinite(tau):
        raise ValueError("tau must be finite")

    def initialize(state):
        query = state["query"]
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must not be empty")
        return {"query": query, "queries": [{"query": query, "reason": "original"}],
                "attempts": [], "rankings": [], "used_queries": {query}, "generation_calls": 0,
                "status": Status.REQUEST_MORE, "raw_draft": "", "rows": [], "versions": {},
                "budget": state.get("budget", 600), "final_prompt_input": "", "included_ids": ()}

    def retrieve(state):
        new = [library.search(variant["query"], k=k, mode=mode) for variant in state["queries"]]
        rankings = [*state["rankings"], *new]
        hits, rrf = _rrf(rankings, k)
        attempt = {"attempt": len(state["attempts"]) + 1, "queries": state["queries"],
                   "hits": [{"chunk_id": c.chunk_id, "score": score, "rank": rank} for c, score, rank in hits],
                   "top_score": max((score for _, score, _ in hits), default=None), "rrf": rrf}
        return {**state, "rankings": rankings, "hits": hits, "attempts": [*state["attempts"], attempt]}

    def grade(state):
        top = state["attempts"][-1]["top_score"]
        sufficient = bool(state["hits"]) and top is not None and top >= tau
        attempts = [*state["attempts"][:-1], {**state["attempts"][-1], "sufficient": sufficient, "tau": tau}]
        return {**state, "sufficient": sufficient, "attempts": attempts,
                "status": Status.OK if sufficient else Status.REQUEST_MORE}

    def rewrite(state):
        remaining = [v for v in rewrite_queries(state["query"]) if v["query"] not in state["used_queries"]]
        subquestions = [v for v in remaining if v["reason"] == "subquestion"]
        queries = subquestions if len(state["attempts"]) == 1 and subquestions else remaining
        return {**state, "queries": queries,
                "used_queries": state["used_queries"] | {v["query"] for v in queries}}

    def equalize(state):
        order = {chunk.chunk_id: i for i, chunk in enumerate(getattr(library, "chunks", []))}
        hits = sorted(state["hits"], key=lambda hit: order.get(hit[0].chunk_id, hit[2]))
        draft = "\n\n".join(chunk.safe_text for chunk, _, _ in hits)
        result = stages.prepare(base, draft, task=state["query"], preset=eq.profile.name, budget=state["budget"])
        for stage in stages.STAGES:
            result = stage(result, result["parts"])
            if result.get("_finished"):
                break
        return {**state, **result}

    graph = StateGraph(dict)
    for name, fn in (("initialize", initialize), ("retrieve", retrieve), ("grade", grade), ("rewrite", rewrite), ("equalize", equalize)):
        graph.add_node(name, fn)
    graph.add_edge(START, "initialize")
    graph.add_edge("initialize", "retrieve")
    graph.add_edge("retrieve", "grade")
    graph.add_conditional_edges("grade", lambda s: "equalize" if s["sufficient"] else "rewrite" if len(s["attempts"]) <= max_retries else END,
                                {"equalize": "equalize", "rewrite": "rewrite", END: END})
    graph.add_conditional_edges("rewrite", lambda s: "retrieve" if s["queries"] else END,
                                {"retrieve": "retrieve", END: END})
    graph.add_edge("equalize", END)
    return ServingGraph(graph.compile(), log_path)
