"""Uncalibrated duck-typed cosine relevance; no model loading or cross-module imports."""
from __future__ import annotations

MATURITY = "incubating"

import math


def make_semantic_relevance(embedder, normalize="minmax", cache=True):
    """minmax maps the theoretical cosine range [-1, 1] to [0, 1].

    none keeps nonnegative cosine (negative cosine is clamped to zero).
    This is not corpus-dependent calibration and does not estimate tau.
    Caches live in this factory instance; create one per request if input retention matters.
    """
    if normalize not in ("minmax", "none"):
        raise ValueError("normalize must be minmax or none")
    query_cache, text_cache = {}, {}

    def vector(raw):
        result = tuple(float(x) for x in raw)
        if not result or not all(math.isfinite(x) for x in result):
            raise ValueError("embedding must contain finite values")
        return result

    def relevance(task):
        if not task or not task.strip():
            return lambda text: 1.0
        if cache and task in query_cache:
            query = query_cache[task]
        else:
            query = vector(embedder.encode_query(task))
            if cache:
                query_cache[task] = query
        scores = {}

        def score(text):
            if cache and text in scores:
                return scores[text]
            if cache and text in text_cache:
                doc = text_cache[text]
            else:
                batch = embedder.encode_documents([text])
                if len(batch) != 1:
                    raise ValueError("embedder returned an unexpected batch size")
                doc = vector(batch[0])
                if cache:
                    text_cache[text] = doc
            if len(query) != len(doc):
                raise ValueError("embedding dimension mismatch")
            denom = math.hypot(*query) * math.hypot(*doc)
            cosine = math.fsum(a * b for a, b in zip(query, doc)) / denom if denom else 0.0
            value = (cosine + 1) / 2 if normalize == "minmax" and denom else cosine
            value = max(0.0, min(1.0, value))
            if cache:
                scores[text] = value
            return value
        return score
    return relevance
