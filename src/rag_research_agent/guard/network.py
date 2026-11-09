"""Process-level guards for learning scripts: no outbound network, no provider keys."""
from __future__ import annotations

MATURITY = "incubating"

import os
import socket

ATTEMPTS: list[str] = []


def block_network() -> None:
    """Fail any outbound TCP connection. Model files must already be in the local cache."""
    def refuse(self, address, *args, **kwargs):  # noqa: ARG001
        ATTEMPTS.append(repr(address))
        raise OSError("network blocked by learning-script guard")

    def refuse_create(address, *args, **kwargs):  # noqa: ARG001
        ATTEMPTS.append(repr(address))
        raise OSError("network blocked by learning-script guard")

    socket.socket.connect = refuse  # type: ignore[method-assign]
    socket.create_connection = refuse_create  # type: ignore[assignment]


def scrub_environment() -> None:
    """memvid auto-embeds when OPENAI_API_KEY is present and enable_embedding is omitted."""
    for key in ("OPENAI_API_KEY", "LANGSMITH_API_KEY", "LANGCHAIN_API_KEY"):
        os.environ.pop(key, None)
    for key in ("LANGSMITH_TRACING", "LANGCHAIN_TRACING_V2"):
        os.environ[key] = "false"
    os.environ["MEMVID_TELEMETRY"] = "0"
