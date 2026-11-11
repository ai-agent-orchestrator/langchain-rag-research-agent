"""Public research facade; implementation and optional dependencies stay in their modules."""
from __future__ import annotations

MATURITY = "incubating"
API_VERSION = "0.1"

from dataclasses import replace
from typing import TYPE_CHECKING

from rag_research_agent.core.research import Draft, ReportSentence, ResearchPlan


if TYPE_CHECKING:
    from rag_research_agent.rag.research_graph import ResearchConfig, ResearchResult, SearchFn

__all__ = [
    "API_VERSION", "run_research", "ResearchConfig", "ResearchResult", "DomainFilter",
    "register", "get_filter", "SearchFn", "keyword_search", "chroma_search",
]


def __getattr__(name: str):
    # Preserve identity of existing public classes/functions without loading the
    # graph (and LangGraph) when only the facade or domain contracts are imported.
    if name in {"ResearchConfig", "ResearchResult", "SearchFn", "keyword_search"}:
        from rag_research_agent.rag import research_graph
        return getattr(research_graph, name)
    if name in {"DomainFilter", "get_filter", "register"}:
        from rag_research_agent.guard import domain_filter
        return getattr(domain_filter, name)
    if name == "chroma_search":
        from rag_research_agent.rag.research_chroma import make_chroma_search
        return make_chroma_search
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def run_research(question: str, *, search: SearchFn, config: ResearchConfig | None = None,
                 checklist: tuple[str, ...] = (), domain: str = "research") -> ResearchResult:
    """Run masked local research; alternate registered domains add outer gates.

    The research default delegates unchanged to the claim-aware graph verifier.
    Other domains screen before retrieval and verify once after the graph. Their
    failed verdict returns a safe note, without an additional retry/model call.
    Callers own masking, the search backend, and any index lifecycle.
    """
    from rag_research_agent.rag.research_graph import ResearchConfig, ResearchResult, ResearchRunner

    cfg = ResearchConfig() if config is None else config
    if domain == "research":
        return ResearchRunner(search, cfg).run(question, tuple(checklist))

    from rag_research_agent.guard.domain_filter import get_filter
    selected = get_filter(domain)
    decision = selected.check_input(question)
    screen = "SCREEN:PASS" if decision.allowed else "SCREEN:BLOCK:" + decision.code
    if not decision.allowed:
        draft = Draft((ReportSentence("요청을 처리할 수 없습니다.", note=True),))
        return ResearchResult(draft.render(), draft, ResearchPlan(()), (), (), (), (),
                              "BLOCKED", (screen,), (), ("screen",))

    result = ResearchRunner(search, cfg).run(question, tuple(checklist))
    verdict = selected.verify(result.draft.body(), tuple(s.text for s in result.sources), decision.branch)
    log = (screen,) + result.log + (("VERIFY:PASS",) if verdict.ok else
                                   tuple("VERIFY:FAIL:" + code for code in verdict.codes))
    if not verdict.ok:
        draft = Draft((ReportSentence("근거와 대조해 검증할 수 있는 답변을 만들지 못했습니다.", note=True),))
        return replace(result, report=draft.render(), draft=draft,
                       verify_codes=tuple(dict.fromkeys(result.verify_codes + verdict.codes)),
                       stopped="VERIFY_FAILED", log=log, path=("screen",) + result.path + ("domain_verify",))
    return replace(result, report=selected.finalize(result.report, decision.branch), log=log,
                   path=("screen",) + result.path + ("domain_verify", "finalize"))
