"""Opt-in research bridge: Library -> relevance gate -> B03 chain/B04 graph -> safe answer.

No FastAPI endpoints, provider selection, model loading or implicit fake fallback.
"""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass
import math

from rag_research_agent.core.contracts import build_query, fingerprint, RetrievalStatus, RetrievalUnavailable
from rag_research_agent.core.types import Status
from rag_research_agent.guard.intake_guard_adapter import IntakeInputPolicy, IntakeOutputPolicy, IntakeMasker
from rag_research_agent.observe.tracing import serving_config, serving_trace_guard
from rag_research_agent.retrieve.gate import RelevanceRule, to_result
from rag_research_agent.rag.answer import (
    DraftRejected, EvidenceStatus, NOT_INVOKED_MODEL, assemble_answer, no_evidence_answer,
)
from rag_research_agent.rag.chain import build_chain
from rag_research_agent.rag.execution import BoundedWorker
from rag_research_agent.rag.graph import build_graph


class GuidanceDisabled(RuntimeError):
    code = "RAG_DISABLED"


class BackboneNotConfigured(RuntimeError):
    code = "BACKBONE_NOT_CONFIGURED"


@dataclass(frozen=True)
class GuidanceEvidence:
    chunk_id: str
    document_id: str
    title: str
    source_version: str
    safe_text: str


@dataclass(frozen=True)
class SearchOutcome:
    status: RetrievalStatus
    evidence: tuple[GuidanceEvidence, ...] = ()


@dataclass(frozen=True)
class GuidanceReply:
    status: Status
    answer: str
    model: str = NOT_INVOKED_MODEL
    evidence_status: EvidenceStatus = EvidenceStatus.NOT_FOUND
    citation_ids: tuple[str, ...] = ()
    generation_calls: int = 0
    retrieval_status: str | None = None
    reason_code: str = ""

    def to_dict(self):
        if self.status == Status.BLOCKED:
            return {"blocked": True, "reasonCode": self.reason_code, "answer": self.answer}
        return {"answer": self.answer, "model": self.model, "evidenceStatus": self.evidence_status.value,
                "citationIds": list(self.citation_ids)}


class GuidancePipeline:
    def __init__(self, library, rule: RelevanceRule, *, index_version, model=None, model_id=None,
                 enabled=False, worker=None, retrieval_timeout=30.0, generation_timeout=30.0,
                 input_policy=None, retrieved_policy=None, output_policy=None, masker=None, k=3):
        if not index_version or not rule.version:
            raise ValueError("explicit index and relevance-rule versions are required")
        if model is not None and not model_id:
            raise ValueError("an injected model requires an explicit model_id")
        if k < 1 or any(not math.isfinite(v) for v in (rule.tau_abs, rule.tau_gap)):
            raise ValueError("invalid retrieval gate")
        self.library, self.rule, self.index_version = library, rule, index_version
        self.model, self.model_id, self.enabled = model, model_id, enabled
        self.worker = worker or BoundedWorker()
        self._owns_worker = worker is None
        self.retrieval_timeout, self.generation_timeout, self.k = retrieval_timeout, generation_timeout, k
        self.input_policy, self.retrieved_policy = input_policy, retrieved_policy
        self.output_policy, self.masker = output_policy, masker

    async def ainvoke(self, request):
        reply, _ = await self._run(request)
        return reply

    async def ainvoke_with_evidence(self, request):
        """(reply, masked evidence texts) for a domain verifier in rag/guardrail_graph.py.
        The texts are the same masked safe_text the model saw; empty when nothing was generated."""
        return await self._run(request)

    async def _run(self, request):
        if not self.enabled:
            raise GuidanceDisabled("RAG is disabled; enable explicitly for synthetic research runs")
        with serving_trace_guard():
            policy = self.input_policy or IntakeInputPolicy()
            material_policy = self.retrieved_policy or IntakeInputPolicy(profile="retrieved")
            output_policy = self.output_policy or IntakeOutputPolicy()
            masker = self.masker or IntakeMasker()
            case_type = request["caseType"]
            if case_type not in {"CIVIL", "CRIMINAL", "FAMILY", "OTHER"}:
                raise ValueError("unknown caseType")
            # clientName is deliberately not read, checked, stored in graph state, or sent anywhere.
            statement, next_step = request["coreStatement"], request.get("desiredNextStep")
            raw_query = build_query(case_type, statement, next_step)
            decision = policy.check(raw_query)
            if not decision.allowed:
                return GuidanceReply(Status.BLOCKED, "요청을 처리할 수 없습니다.", reason_code=decision.reason), ()
            query = build_query(case_type, masker.mask(statement), masker.mask(next_step) if next_step else None)

            def checked_output(text):
                decision = output_policy.check(text)
                if not decision.allowed:
                    raise DraftRejected("output policy rejected a field")
                return masker.mask(text)

            def search_sync(text):
                try:
                    hits = self.library.search(text, k=max(self.k * 3, 10), mode=self.rule.mode.value)
                except RetrievalUnavailable:
                    raise
                except Exception as exc:
                    raise RetrievalUnavailable("retrieval backend failed") from exc
                known = {chunk.chunk_id: chunk for chunk in self.library.chunks}
                usable, safe = [], {}
                for chunk, score, rank in hits:
                    if (known.get(chunk.chunk_id) != chunk or fingerprint(chunk.safe_text) != chunk.content_hash
                            or not math.isfinite(score) or rank < 1):
                        raise RetrievalUnavailable("retrieval provenance or score mismatch")
                    if not material_policy.check(chunk.safe_text).allowed:
                        continue
                    if masker.mask(chunk.chunk_id) != chunk.chunk_id or masker.mask(chunk.document_id) != chunk.document_id:
                        raise RetrievalUnavailable("source identifiers contain personal data")
                    safe[chunk.chunk_id] = GuidanceEvidence(chunk.chunk_id, chunk.document_id,
                                                          checked_output(chunk.title), checked_output(chunk.source_version),
                                                          masker.mask(chunk.safe_text))
                    usable.append((chunk, score, rank))
                outcome = to_result(usable, self.rule, self.index_version, self.k)
                return SearchOutcome(outcome.status, tuple(safe[e.chunk.chunk_id] for e in outcome.evidence))

            async def retrieve(text):
                return await self.worker.run(search_sync, text, timeout=self.retrieval_timeout)

            async def generate(text, evidence):
                if self.model is None:
                    raise BackboneNotConfigured("O2: select and inject a backbone before generation")
                # A dedicated slot covers synchronous model work until it actually finishes.
                return await self.worker.run(lambda: build_chain(self.model).invoke(
                    {"intake": text, "evidence": evidence}, config=serving_config()), timeout=self.generation_timeout)

            state = await build_graph(retrieve, generate).ainvoke({"request_text": query}, config=serving_config())
            if state["draft"] is None:
                return GuidanceReply(Status.REQUEST_MORE, no_evidence_answer(checked_output),
                                     retrieval_status=state["retrieval_status"]), ()
            answer = assemble_answer(state["draft"], state["evidence"], checked_output)
            reply = GuidanceReply(Status.OK, answer, self.model_id, EvidenceStatus.FOUND,
                                  tuple(dict.fromkeys(state["draft"].citation_ids)), state["generation_calls"],
                                  state["retrieval_status"])
            return reply, tuple(getattr(e, "safe_text", str(e)) for e in state["evidence"])

    async def aclose(self):
        if self._owns_worker:
            await self.worker.aclose()
