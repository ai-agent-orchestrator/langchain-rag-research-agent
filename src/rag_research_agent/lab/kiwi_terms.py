"""Optional Korean morphology experiment; never used by stable defaults."""
from __future__ import annotations

MATURITY = "lab"

from functools import lru_cache
from rag_research_agent.core.lexical import lex_terms

UNITS = {"원", "달러", "억", "조", "만", "명", "건", "년", "월", "일", "개월", "배", "%"}


class KiwiUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _analyzer():
    try:
        from kiwipiepy import Kiwi
    except ImportError as exc:
        raise KiwiUnavailable('Kiwi 미설치: pip install -e ".[kiwi]" 후 실행하세요') from exc
    return Kiwi()


def kiwi_terms(query, analyzer=None):
    tokens = list((analyzer or _analyzer()).tokenize(query))
    out, i = [], 0
    while i < len(tokens):
        token = tokens[i]
        form, tag = token.form, token.tag.split("-", 1)[0]
        if tag == "SN" and i + 1 < len(tokens) and tokens[i + 1].form in UNITS:
            form += tokens[i + 1].form
            i += 1
        if tag.startswith("NN") or tag in ("VV", "VX", "SL", "SN"):
            for term in lex_terms(form):
                if term not in out:
                    out.append(term)
        i += 1
    return out
