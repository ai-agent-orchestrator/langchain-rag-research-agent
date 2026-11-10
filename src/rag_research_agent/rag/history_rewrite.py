"""Rule-based follow-up expansion without models or network access.

History contains user queries only, ordered oldest to newest. Personal information
masking is the caller's responsibility, outside this module, for both inputs.
"""
from __future__ import annotations

MATURITY = "incubating"

import re
from typing import Sequence

from rag_research_agent.core.lexical import lex_terms


_DEMONSTRATIVE = re.compile(
    r"(?<!\w)(?:그거|그건|그것|그게|이것|이거|이건|해당|위의)"
    r"(?:은|는|이|가|을|를|의|에|에서|으로|로|도|만|부터|까지)?(?!\w)"
)


def rewrite_with_history(
    query: str, history: Sequence[str], *, max_turns: int = 3
) -> tuple[str, list[str]]:
    """Return (expanded query, applied rule reasons), preserving query verbatim.

    Retain at most the newest max_turns user turns; only the immediately previous
    query supplies keywords. Zero disables history; negative limits are invalid.
    A demonstrative or a query of at most 10 non-whitespace characters triggers
    expansion. Append lex_terms absent from the current query, in their original
    order. Empty queries/history/keywords produce no change and no reasons.
    Reasons are stable identifiers: ``demonstrative`` and ``short_query``; both
    are returned when both rules apply, but only if keywords were appended.
    No older-turn fallback, normalization of the original, or input mutation.
    """
    if max_turns < 0:
        raise ValueError("max_turns must be non-negative")
    if not query.strip() or not history or max_turns == 0:
        return query, []

    reasons = []
    if _DEMONSTRATIVE.search(query):
        reasons.append("demonstrative")
    if len("".join(query.split())) <= 10:
        reasons.append("short_query")
    if not reasons:
        return query, []

    recent = history[-max_turns:]
    current_terms = set(lex_terms(query))
    keywords = [term for term in lex_terms(recent[-1]) if term not in current_terms]
    if not keywords:
        return query, []
    return query + " " + " ".join(keywords), reasons
