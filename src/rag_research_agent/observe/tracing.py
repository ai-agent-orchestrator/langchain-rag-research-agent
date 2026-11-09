"""B05 tracing boundary.

Serving: remote tracing is OFF in code, whatever the environment says. Every graph/chain
call made for a request runs inside `serving_trace_guard()`.
Evaluation: remote tracing is allowed only in synthetic evaluation scripts, through an
explicit client whose inputs, outputs and metadata pass an allowlist.
"""
from __future__ import annotations

MATURITY = "incubating"

from contextlib import contextmanager
from typing import Any, Iterator

from langsmith import Client
from langsmith.run_helpers import tracing_context

# Keys that may leave the PC from synthetic evaluation runs. Values are still truncated.
ALLOWED_KEYS = {"item_id", "split", "type", "mode", "status", "route", "retrieval_status",
                "evidence_status", "document_ids", "citation_ids", "generation_calls", "index_version",
                "prompt_version", "latency_ms", "hit", "error_code"}
REDACTED = "[redacted]"


def serving_config() -> dict[str, Any]:
    """Run config for request-time graph calls: no callbacks, neutral names, no metadata."""
    return {"callbacks": [], "run_name": "guidance", "tags": [], "metadata": {}}


@contextmanager
def serving_trace_guard() -> Iterator[None]:
    """Disable LangSmith tracing for everything inside, even if LANGSMITH_TRACING=true."""
    with tracing_context(enabled=False):
        yield


def allowlist(payload: Any) -> Any:
    """Keep allowlisted keys (recursively), redact everything else, cap string length."""
    if isinstance(payload, dict):
        return {k: (allowlist(v) if k in ALLOWED_KEYS else REDACTED) for k, v in payload.items()}
    if isinstance(payload, (list, tuple)):
        return [allowlist(v) for v in payload][:20]
    if isinstance(payload, str):
        return payload[:120]
    if isinstance(payload, (int, float, bool)) or payload is None:
        return payload
    return REDACTED


def evaluation_client(api_key: str | None = None) -> Client:
    """Explicit client for synthetic evaluation only. Inputs/outputs/metadata pass the allowlist."""
    return Client(api_key=api_key, hide_inputs=allowlist, hide_outputs=allowlist, hide_metadata=allowlist)
