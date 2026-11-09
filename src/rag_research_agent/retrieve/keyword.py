"""Keyword-baseline term handling for memvid lex search."""
from __future__ import annotations

MATURITY = "incubating"

import re

_CASE_TYPES = {"CIVIL", "CRIMINAL", "FAMILY", "OTHER"}


def lex_terms(query: str) -> list[str]:
    """Whitespace terms for the keyword baseline, without the caseType label, mask tokens,
    punctuation or 1-character fragments. memvid query operators are never passed through."""
    out: list[str] = []
    for raw in query.split():
        term = re.sub(r"[^\w가-힣]", "", raw)
        if len(term) < 2 or term in _CASE_TYPES or term.upper() in {"OR", "AND", "NOT"} or term.isupper():
            continue
        if term not in out:
            out.append(term)
    return out
