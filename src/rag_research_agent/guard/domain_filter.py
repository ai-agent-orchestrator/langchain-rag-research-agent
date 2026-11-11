"""Domain filter contract: the swappable part of the LangGraph guardrail (docs/DOMAIN_FILTERS.ko.md).

Each domain hallucinates in its own way (legal: timelines and repealed statutes; medical: definitive
diagnoses and missing contraindications; research: lost causality and shallow generalisation; local
administration: ignored regional exceptions and outdated forms). The graph shape stays the same
(route -> local RAG -> rule filter); only the filter plugged into it changes.

A filter is pure Python: no model, no network, no imports from other modules. It returns codes only,
never request text, so graph state and logs stay free of personal data.
"""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass
import importlib
from typing import Callable, Protocol, runtime_checkable


@dataclass(frozen=True)
class InputDecision:
    allowed: bool
    code: str = ""              # why it was blocked or redirected, e.g. "EMPTY_INPUT", "EMERGENCY"
    branch: str = "default"     # isolated path inside the domain, e.g. "civil" / "criminal"


@dataclass(frozen=True)
class Issue:
    code: str                   # e.g. "UNSUPPORTED_NUMBER", "CAUSAL_LOSS"
    retryable: bool             # True: a new generation may fix it; False: return the safe answer
    count: int = 1


@dataclass(frozen=True)
class Verdict:
    ok: bool
    issues: tuple[Issue, ...] = ()
    scores: tuple[tuple[str, float], ...] = ()   # named measurements, e.g. ("density", 0.62)

    @property
    def codes(self) -> tuple[str, ...]:
        return tuple(i.code for i in self.issues)

    @property
    def retryable(self) -> bool:
        return bool(self.issues) and all(i.retryable for i in self.issues)


@runtime_checkable
class DomainFilter(Protocol):
    """What every domain filter provides. Version every rule change (results must stay explainable)."""
    name: str
    version: str

    def check_input(self, text: str) -> InputDecision: ...

    def verify(self, answer: str, evidence: tuple[str, ...], branch: str = "default") -> Verdict: ...

    def finalize(self, answer: str, branch: str = "default") -> str: ...


_REGISTRY: dict[str, Callable[[], DomainFilter]] = {}
# Built-in filters register themselves on import; get_filter imports them on first use.
# Legal, medical and local-administration filters plug in here later (docs/DOMAIN_FILTERS.ko.md 4).
BUILTINS = {"research": "rag_research_agent.guard.research_filter"}


def register(name: str, factory: Callable[[], DomainFilter]) -> None:
    if not name or name in _REGISTRY:
        raise ValueError(f"domain filter name missing or already registered: {name!r}")
    _REGISTRY[name] = factory


def get_filter(name: str) -> DomainFilter:
    if name not in _REGISTRY and name in BUILTINS:
        importlib.import_module(BUILTINS[name])
    try:
        return _REGISTRY[name]()
    except KeyError:
        raise KeyError(f"unknown domain filter {name!r}; registered: {sorted(_REGISTRY)}") from None


def registered() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))
