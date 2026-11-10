"""Assemble chunk experiment diagnostics without model encoding or source mutations."""
from rag_research_agent.ingest.token_windows import token_windows
from rag_research_agent.ingest.paragraphs import paragraph_chunks

MATURITY = "incubating"


def chunk_diagnostics(docs, embedder, size=None, overlap=0, items=()):
    if size is None and overlap:
        raise ValueError("overlap requires chunk_size")
    chunks = [c for id, title, text in docs for c in (
        token_windows(id, title, text, embedder.count_tokens, size, overlap) if size is not None
        else paragraph_chunks(id, title, text))]
    limit = getattr(embedder, "max_tokens", 512)
    over = [c.chunk_id for c in chunks if embedder.count_tokens(c.safe_text) > limit]
    split_ids = []
    for item in items:
        if any(r.get("quote") and not any(c.document_id == r["source"] and r["quote"] in c.safe_text for c in chunks)
               for r in item.get("relevant", [])):
            split_ids.append(item["id"])
    return {"chunk_size": size, "overlap": overlap, "unit": "tokens", "chunks": len(chunks),
            "quote_split_questions": len(split_ids), "quote_split_ids": split_ids,
            "over_limit_chunks": len(over), "over_limit_ids": over, "token_limit": limit,
            "token_limit_is_simulated": "fake" in embedder.model_id.lower()}
