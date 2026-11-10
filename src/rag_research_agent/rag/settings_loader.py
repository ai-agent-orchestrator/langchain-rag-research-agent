"""Load RuntimeSettings from defaults < JSON file < environment (N7), and turn them into constructor arguments.

Order: code defaults, then an optional UTF-8 JSON object file, then RRA_* environment variables.
No .env file is read and no secret fields exist. Nothing here is wired into a pipeline automatically;
callers opt in with relevance_rule(), worker_kwargs() and pipeline_kwargs().
"""
from __future__ import annotations

MATURITY = "incubating"

import json
import os
from pathlib import Path
from typing import Mapping

from rag_research_agent.core.contracts import RetrievalMode
from rag_research_agent.core.settings import RuntimeSettings, SettingsError, env_layer, settings_from_layers
from rag_research_agent.retrieve.gate import RelevanceRule


def load_settings(path: str | Path | None = None, environ: Mapping[str, str] | None = None,
                  *, prefix: str = "RRA_") -> RuntimeSettings:
    layers = []
    if path is not None:
        file = Path(path)
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raise SettingsError(f"settings file not found: {file}") from None
        except json.JSONDecodeError as exc:
            raise SettingsError(f"settings file is not valid JSON: {file} (line {exc.lineno})") from None
        if not isinstance(data, dict):
            raise SettingsError(f"settings file must contain a JSON object: {file}")
        layers.append((str(file), data))
    layers.append(("environment", env_layer(os.environ if environ is None else environ, prefix)))
    return settings_from_layers(*layers)


def relevance_rule(settings: RuntimeSettings) -> RelevanceRule:
    return RelevanceRule(RetrievalMode(settings.retrieval_mode), settings.tau_abs, settings.tau_gap,
                         settings.rule_version)


def worker_kwargs(settings: RuntimeSettings) -> dict:
    """Arguments for rag.execution.BoundedWorker(...)."""
    return {"concurrent": settings.worker_slots, "waiters": settings.queue_limit,
            "admission_timeout": settings.admission_timeout_s}


def pipeline_kwargs(settings: RuntimeSettings) -> dict:
    """Keyword arguments for rag.guidance.GuidancePipeline(library, rule, **kwargs) (model/enabled stay explicit)."""
    return {"index_version": settings.index_version, "retrieval_timeout": settings.retrieval_timeout_s,
            "generation_timeout": settings.generation_timeout_s, "k": settings.k}
