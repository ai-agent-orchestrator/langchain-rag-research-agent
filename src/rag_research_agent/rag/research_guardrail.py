"""Opt-in bridge from a masked, local ResearchRunner to the guardrail RAG node.

The caller owns masking of questions, checklist entries and the injected search.
No store, model or server configuration is selected here.
"""
from __future__ import annotations

MATURITY = "incubating"

import asyncio
from dataclasses import dataclass
import math

from rag_research_agent.core.types import Status
from rag_research_agent.guard.domain_filter import get_filter
from rag_research_agent.rag.answer import EvidenceStatus
from rag_research_agent.rag.guidance import GuidanceReply
from rag_research_agent.rag.guardrail_graph import (
    GuardrailRunner, VERIFY_FAILED_ANSWER,
)
from rag_research_agent.rag.research_graph import ResearchResult, ResearchRunner


def tokens_to_cost(tokens: int, tokens_per_unit: float = 1000.0) -> float:
    """Convert estimated tokens to local cost units (not currency)."""
    if not math.isfinite(tokens_per_unit) or tokens_per_unit <= 0:
        raise ValueError("tokens_per_unit must be finite and positive")
    if not math.isfinite(tokens) or tokens < 0:
        raise ValueError("tokens must be finite and nonnegative")
    return tokens / tokens_per_unit


@dataclass(frozen=True)
class ResearchGuidanceReply(GuidanceReply):
    """Internal per-call metadata; inherited to_dict omits cost and review codes."""
    shadow_tokens: int = 0
    research_verify_codes: tuple[str, ...] = ()


def to_guidance(result: ResearchResult) -> tuple[ResearchGuidanceReply, tuple[str, ...]]:
    """Never expose an unverified, stopped or interrupted research draft."""
    failed = bool(result.verify_codes)
    incomplete = bool(result.stopped or result.interrupts or not result.draft.sentences)
    safe = failed or incomplete
    cited_claims = {cid for sentence in result.draft.sentences for cid in sentence.claim_ids}
    cited_sources = {c.source_id for c in result.claims if c.claim_id in cited_claims}
    # Refine can discard retrieved injection passages. Only admitted claims are evidence.
    admitted_sources = {c.source_id for c in result.claims}
    evidence = tuple(s.text for s in result.sources if s.source_id in admitted_sources)
    reply = ResearchGuidanceReply(
        status=Status.REQUEST_MORE if safe else Status.OK,
        answer=VERIFY_FAILED_ANSWER if safe else result.report,
        evidence_status=EvidenceStatus.NOT_FOUND if safe or not evidence else EvidenceStatus.FOUND,
        citation_ids=() if safe else tuple(s.source_id for s in result.sources if s.source_id in cited_sources),
        reason_code="VERIFY_FAILED" if failed else (result.stopped or "RESEARCH_INCOMPLETE") if incomplete else "",
        retrieval_calls=sum(kind == "search" for _, kind, _ in result.cost),
        shadow_tokens=result.shadow_tokens,
        research_verify_codes=tuple(result.verify_codes),
    )
    return reply, () if safe else evidence


class ResearchGuardrailAdapter:
    """Async RAG callable and matching cost function; no shared last-result state.

    Use GuardrailRunner(adapter, domain=get_filter("research"), cost=adapter.cost),
    or adapter.guardrail(). Existing guardrail defaults are unchanged.
    Checkpoint/review sessions require a separate resume-aware integration.
    """

    def __init__(self, research: ResearchRunner, *, tokens_per_unit: float = 1000.0):
        tokens_to_cost(0, tokens_per_unit)
        if research.checkpointer is not None or research.cfg.review_plan:
            raise ValueError("guardrail adapter requires non-checkpointed research")
        self.research = research
        self.tokens_per_unit = tokens_per_unit

    async def __call__(self, request: dict):
        question = request.get("coreStatement", "")
        checklist = request.get("checklist", ())
        if not isinstance(question, str):
            raise TypeError("coreStatement must be a masked string")
        if not isinstance(checklist, (list, tuple)) or any(not isinstance(m, str) for m in checklist):
            raise TypeError("checklist must contain masked strings")
        result = await asyncio.to_thread(self.research.run, question, tuple(checklist))
        return to_guidance(result)

    def cost(self, reply: GuidanceReply | None) -> float:
        # Failed calls have no ResearchResult/token ledger; retain the guardrail's
        # default failed-call estimate rather than claiming zero cost.
        if reply is None:
            return 0.1
        if not isinstance(reply, ResearchGuidanceReply):
            raise TypeError("research cost requires ResearchGuidanceReply")
        return tokens_to_cost(reply.shadow_tokens, self.tokens_per_unit)

    def guardrail(self, **options) -> GuardrailRunner:
        """Compile the existing guardrail with the research filter and token cost."""
        return GuardrailRunner(self, domain=get_filter("research"), cost=self.cost, **options)
