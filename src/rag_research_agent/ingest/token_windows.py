"""Verbatim token-budget windows for controlled chunk-size experiments."""
from rag_research_agent.core.contracts import Chunk

MATURITY = "incubating"


def token_windows(doc_id, title, text, count, size, overlap=0):
    if size < 1 or not 0 <= overlap < size:
        raise ValueError("require chunk_size > overlap >= 0")
    chunks, start = [], 0
    while start < len(text):
        # Find a fitting prefix; verify it with the actual injected tokenizer.
        lo, hi = start + 1, len(text)
        end = start
        while lo <= hi:
            mid = (lo + hi) // 2
            if count(text[start:mid]) <= size:
                end, lo = mid, mid + 1
            else:
                hi = mid - 1
        if end == start:
            raise ValueError("one character exceeds token budget")
        body = text[start:end]
        if body.strip():
            chunks.append(Chunk(doc_id, f"{doc_id}:t{len(chunks):04d}", "v1", "library", title,
                                body, max(1, count(body)), f"token-window-v1:{size}/{overlap}", "none", "none"))
        if end == len(text):
            break
        next_start = end
        while overlap and next_start > start + 1 and count(text[next_start - 1:end]) <= overlap:
            next_start -= 1
        start = next_start
    return chunks
