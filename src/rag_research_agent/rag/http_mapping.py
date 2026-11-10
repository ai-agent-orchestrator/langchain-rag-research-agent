"""Pipeline result or exception -> (status_code, body, headers) (N11). No web framework is imported.

Rules (docs/MODULE_DESIGN.ko.md 2-3): policy blocks and technical errors are never mixed;
RETRIEVAL_UNAVAILABLE is 503 and is never turned into "no evidence".
Bodies reuse GuidanceReply.to_dict() (already checked and masked) for replies. Error bodies carry a
fixed code only: no exception message, no query text, no stack.
"""
from __future__ import annotations

MATURITY = "incubating"

from typing import Any, Mapping

from rag_research_agent.core.contracts import RetrievalUnavailable
from rag_research_agent.core.types import Status
from rag_research_agent.rag.answer import DraftRejected
from rag_research_agent.rag.execution import InferenceCapacityExceeded, InferenceTimeout
from rag_research_agent.rag.guidance import BackboneNotConfigured, GuidanceDisabled, GuidanceReply

CASE_TYPES = ("CIVIL", "CRIMINAL", "FAMILY", "OTHER")
RETRY_AFTER_RETRIEVAL_S = 30
RETRY_AFTER_CAPACITY_S = 5

# Reply statuses GuidancePipeline produces. Every one is a 200: "no evidence" and "blocked by policy"
# are answers, not server failures (blocked keeps the existing {"blocked": true, "reasonCode"} body).
REPLY_STATUS = {Status.OK: 200, Status.REQUEST_MORE: 200, Status.BLOCKED: 200}

# Exception class -> (status, code, retry_after seconds or None). Order matters: subclasses first.
ERRORS: tuple[tuple[type[BaseException], int, str, int | None], ...] = (
    (RetrievalUnavailable, 503, "RETRIEVAL_UNAVAILABLE", RETRY_AFTER_RETRIEVAL_S),
    (InferenceCapacityExceeded, 503, "GENERATION_CAPACITY_EXCEEDED", RETRY_AFTER_CAPACITY_S),
    (InferenceTimeout, 504, "INFERENCE_TIMEOUT", None),
    (BackboneNotConfigured, 503, "BACKBONE_NOT_CONFIGURED", None),
    (GuidanceDisabled, 503, "RAG_DISABLED", None),
    (DraftRejected, 502, "AI_DRAFT_REJECTED", None),
)
GUARDRAIL_STOPPED = (503, "GUARDRAIL_STOPPED")
INVALID_REQUEST = (400, "INVALID_REQUEST")
INTERNAL_ERROR = (500, "INTERNAL_ERROR")

JSON = {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}


def _error(status: int, code: str, retry_after: int | None = None) -> tuple[int, dict, dict]:
    headers = dict(JSON)
    if retry_after is not None:
        headers["Retry-After"] = str(retry_after)
    return status, {"error": code}, headers


def validate_request(request: Any) -> tuple[int, dict, dict] | None:
    """Return a 400 response for a malformed request, or None. Run before calling the pipeline, so a
    ValueError raised later inside the pipeline is never mistaken for a client error."""
    if not isinstance(request, Mapping):
        return _error(*INVALID_REQUEST)
    if request.get("caseType") not in CASE_TYPES:
        return _error(*INVALID_REQUEST)
    statement = request.get("coreStatement")
    if not isinstance(statement, str) or not statement.strip():
        return _error(*INVALID_REQUEST)
    next_step = request.get("desiredNextStep")
    if next_step is not None and not isinstance(next_step, str):
        return _error(*INVALID_REQUEST)
    return None


def map_reply(reply: GuidanceReply) -> tuple[int, dict, dict]:
    status = REPLY_STATUS.get(reply.status)
    if status is None:                       # a status this adapter does not know is a server bug
        return _error(*INTERNAL_ERROR)
    return status, reply.to_dict(), dict(JSON)


def map_exception(error: BaseException) -> tuple[int, dict, dict]:
    if getattr(error, "code", None) == GUARDRAIL_STOPPED[1]:
        return _error(*GUARDRAIL_STOPPED)
    for kind, status, code, retry_after in ERRORS:
        if isinstance(error, kind):
            return _error(status, code, retry_after)
    return _error(*INTERNAL_ERROR)


def map_outcome(outcome: Any) -> tuple[int, dict, dict]:
    """One entry point: a GuidanceReply, a guardrail result (.reply/.stop_code/.error), or an exception."""
    if isinstance(outcome, BaseException):
        return map_exception(outcome)
    if isinstance(outcome, GuidanceReply):
        return map_reply(outcome)
    stop_code = getattr(outcome, "stop_code", None)
    if stop_code:
        cause = getattr(outcome, "error", None)
        # A stop caused by a known failure reports that failure (e.g. 503 RETRIEVAL_UNAVAILABLE after retries);
        # a stop on loop/cost limits alone is GUARDRAIL_STOPPED.
        return map_exception(cause) if isinstance(cause, BaseException) else _error(*GUARDRAIL_STOPPED)
    reply = getattr(outcome, "reply", None)
    if isinstance(reply, GuidanceReply):
        return map_reply(reply)
    return _error(*INTERNAL_ERROR)
