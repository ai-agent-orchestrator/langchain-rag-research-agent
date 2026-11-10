import pytest
from types import SimpleNamespace
from rag_research_agent.ingest.token_windows import token_windows
from rag_research_agent.rag.learning import chunk_diagnostics


def test_verbatim_windows_overlap_recovers_boundary_quote():
    emb = SimpleNamespace(count_tokens=len, max_tokens=6, model_id="synthetic")
    docs = [("doc", "title", "abcdefghij")]
    items = [{"id": "q", "relevant": [{"source": "doc", "quote": "defg"}]}]
    no = chunk_diagnostics(docs, emb, 6, 0, items)
    yes = chunk_diagnostics(docs, emb, 6, 3, items)
    assert no["quote_split_questions"] == 1 and yes["quote_split_questions"] == 0
    assert yes["over_limit_chunks"] == 0
    assert chunk_diagnostics(docs, emb, 10)["over_limit_chunks"] == 1
    assert [c.safe_text for c in token_windows("doc", "title", "abcdefghij", len, 6, 3)] == ["abcdef", "defghi", "ghij"]
    with pytest.raises(ValueError):
        token_windows("doc", "t", "abc", len, 2, 2)
