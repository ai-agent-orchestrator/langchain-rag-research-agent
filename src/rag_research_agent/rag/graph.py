"""B04 LangGraph workflow: retrieve -> (evidence) generate | (no evidence) ask_for_materials.

- The graph is compiled once (lifespan) and invoked with a fresh state per request; no
  checkpointer, no shared mutable state, no loops or retries.
- A retrieval failure raises out of the graph (mapped to 503 by the service). It is never
  turned into the no-evidence branch.
- The no-evidence branch makes zero model calls. The server, not the model, sets the status.
- Security checks are not graph nodes: the service enforces them before and after the graph.
"""
from __future__ import annotations

MATURITY = "incubating"

from typing import Any, Awaitable, Callable, Literal, Optional, Protocol, Sequence, TypedDict

from langgraph.graph import END, START, StateGraph

from rag_research_agent.rag.answer import EvidenceStatus, GuidanceDraft


class RetrievalOutcome(Protocol):
    status: Any          # "OK" | "EMPTY" | "BELOW_THRESHOLD" (str or StrEnum)
    evidence: Sequence[Any]


class GuidanceState(TypedDict, total=False):
    request_text: str                       # already checked and masked by the service
    retrieval_status: str
    evidence: list[Any]
    evidence_status: EvidenceStatus
    draft: Optional[GuidanceDraft]
    generation_calls: int
    route: Literal["generate", "ask_for_materials"]


Retrieve = Callable[[str], Awaitable[RetrievalOutcome]]
Generate = Callable[[str, Sequence[Any]], Awaitable[GuidanceDraft]]


def build_graph(retrieve: Retrieve, generate: Generate):
    async def retrieve_node(state: GuidanceState) -> GuidanceState:
        outcome = await retrieve(state["request_text"])   # exceptions propagate on purpose
        status = str(getattr(outcome.status, "value", outcome.status))
        if status not in {"OK", "EMPTY", "BELOW_THRESHOLD"}:
            raise ValueError(f"unknown retrieval status: {status}")
        evidence = list(outcome.evidence) if status == "OK" else []
        if status == "OK" and not evidence:
            raise ValueError("OK retrieval without evidence")
        return {"retrieval_status": status, "evidence": evidence, "generation_calls": 0}

    def route(state: GuidanceState) -> str:
        return "generate" if state["retrieval_status"] == "OK" else "ask_for_materials"

    async def generate_node(state: GuidanceState) -> GuidanceState:
        draft = await generate(state["request_text"], state["evidence"])
        return {"draft": draft, "evidence_status": EvidenceStatus.FOUND, "route": "generate",
                "generation_calls": state.get("generation_calls", 0) + 1}

    async def ask_for_materials_node(state: GuidanceState) -> GuidanceState:
        return {"draft": None, "evidence": [], "evidence_status": EvidenceStatus.NOT_FOUND,
                "route": "ask_for_materials"}

    graph = StateGraph(GuidanceState)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("generate", generate_node)
    graph.add_node("ask_for_materials", ask_for_materials_node)
    graph.add_edge(START, "retrieve")
    graph.add_conditional_edges("retrieve", route, {"generate": "generate",
                                                    "ask_for_materials": "ask_for_materials"})
    graph.add_edge("generate", END)
    graph.add_edge("ask_for_materials", END)
    return graph.compile()
