"""LAB: compare dense, lexical, RRF and normalized weighted fusion on identical candidates."""
import math

MATURITY = "lab"


def search(library, query, k, method="vector", alpha=.5, rrf_k=60):
    if method not in {"lex", "vector", "rrf", "weighted"}:
        raise ValueError("unknown retrieval method")
    if not math.isfinite(alpha) or not 0 <= alpha <= 1 or rrf_k <= 0:
        raise ValueError("require alpha in [0,1] and rrf_k > 0")
    if method in {"lex", "vector"}:
        return library.search(query, k=k, mode=method)
    # Full candidate sets keep candidate truncation from confounding fusion comparisons.
    width = max(k, len(library.chunks))
    vector = library.search(query, k=width, mode="vector")
    lexical = library.search(query, k=width, mode="lex")
    def key(chunk):
        return getattr(chunk, "chunk_id", (chunk.document_id, chunk.safe_text))
    chunks = {key(c): c for c, _, _ in vector + lexical}
    vectors = {key(c): s for c, s, _ in vector}
    lex = {key(c): s for c, s, _ in lexical}
    if any(not math.isfinite(s) for s in list(vectors.values()) + list(lex.values())):
        raise ValueError("non-finite retrieval score")
    if method == "weighted":
        maximum = max([0.] + list(lex.values()))
        # Lexical scores must be nonnegative. ChromaIndex returns term-match counts.
        if any(s < 0 for s in lex.values()):
            raise ValueError("weighted fusion requires nonnegative keyword scores")
        scores = {cid: alpha * (max(-1., min(1., vectors[cid])) + 1) / 2 if cid in vectors else 0 for cid in chunks}
        for cid in scores:
            scores[cid] += (1 - alpha) * lex.get(cid, 0) / maximum if maximum else 0
        # At endpoints missing/zero-score documents must not inflate the lexical candidate set.
        if alpha == 0:
            scores = {cid: s for cid, s in scores.items() if lex.get(cid, 0) > 0}
    else:
        scores = {}
        for ranking in (vector, lexical):
            seen = set()
            for rank, (chunk, _, _) in enumerate(ranking, 1):
                cid = key(chunk)
                if cid not in seen:
                    scores[cid] = scores.get(cid, 0) + 1 / (rrf_k + rank)
                    seen.add(cid)
    ordered = sorted(scores, key=lambda cid: (-scores[cid], str(cid)))[:k]
    return [(chunks[cid], scores[cid], i) for i, cid in enumerate(ordered, 1)]
