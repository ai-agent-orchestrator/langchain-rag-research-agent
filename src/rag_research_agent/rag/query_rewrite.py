"""Bounded deterministic query variants, without a language model."""
from __future__ import annotations

MATURITY = "incubating"

import re
from rag_research_agent.core.lexical import lex_terms


def rewrite_queries(query):
    original = " ".join(query.split())
    seen, variants = {original}, []
    def add(text, reason):
        text = " ".join(text.split()).strip(" ,，")
        if text and text not in seen:
            seen.add(text)
            variants.append({"query": text, "reason": reason})
    pieces = re.split(r"\s+(?:그리고|또)\s+|[,，]", query)
    if len(pieces) > 1:
        for piece in pieces[:5]:
            add(piece, "subquestion")
    add(" ".join(lex_terms(query)), "keywords")
    add(re.sub(r"\d+(?:[.,]\d+)*\s*(?:년|개월|월|일|분기|%p?|배)?", " ", query), "without_numeric_period")
    return variants
