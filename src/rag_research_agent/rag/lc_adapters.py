"""LangChain exits over existing public APIs; no retrieval or filtering logic is duplicated."""
from __future__ import annotations

MATURITY = "incubating"

from typing import Any, Literal
from pydantic import Field
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_core.tools import StructuredTool

from rag_research_agent.observe.tracing import serving_trace_guard
from rag_research_agent.rag.equalizer_graph import ServingGraph
from rag_research_agent.rag.profile import Equalizer


def _config(config):
    return {**(config or {}), "callbacks": [], "tags": [], "metadata": {}}


class LibraryRetriever(BaseRetriever):
    library: Any
    k: int = Field(default=8, gt=0)
    mode: Literal["hybrid", "vector", "lex"] = "hybrid"

    def _get_relevant_documents(self, query, *, run_manager):
        return [Document(page_content=chunk.safe_text,
                         metadata={"chunk_id": chunk.chunk_id, "document_id": chunk.document_id,
                                   "title": chunk.title, "score": score, "rank": rank})
                for chunk, score, rank in self.library.search(query, self.k, self.mode)]

    def invoke(self, input, config=None, **kwargs):
        with serving_trace_guard():
            return super().invoke(input, config=_config(config), **kwargs)

    async def ainvoke(self, input, config=None, **kwargs):
        with serving_trace_guard():
            return await super().ainvoke(input, config=_config(config), **kwargs)


class EqualizerRunnable(ServingGraph):
    def __init__(self, profile="research", budget=600):
        def run(value):
            request = {"text": value} if isinstance(value, str) else value
            brief, trace = Equalizer.from_profile(profile).brief(request["text"], task=request.get("task"), budget=budget)
            return {"brief": brief.final_prompt_input, "status": brief.status.value,
                    "kept_ids": list(brief.included_ids), "excluded": list(brief.excluded)}
        super().__init__(RunnableLambda(run), log_path=None)


class _ServingTool(StructuredTool):
    def invoke(self, input, config=None, **kwargs):
        with serving_trace_guard():
            return super().invoke(input, config=_config(config), **kwargs)

    async def ainvoke(self, input, config=None, **kwargs):
        with serving_trace_guard():
            return await super().ainvoke(input, config=_config(config), **kwargs)


def library_brief_tool(library, profile="research"):
    def research_brief(question: str) -> str:
        brief, trace, hits = library.brief(question, profile=profile)
        return brief.final_prompt_input
    return _ServingTool.from_function(research_brief, name="research_brief",
                                      description="서재에서 근거를 검색하고 선택한 프로필의 추출 브리프를 반환합니다.")


def make_research_chain(library, profile="research", budget=600):
    retriever = LibraryRetriever(library=library)
    chain = ({"documents": retriever, "task": RunnablePassthrough()}
             | RunnableLambda(lambda value: {"text": "\n\n".join(doc.page_content for doc in value["documents"]),
                                             "task": value["task"]})
             | EqualizerRunnable(profile, budget))
    return ServingGraph(chain, log_path=None)
