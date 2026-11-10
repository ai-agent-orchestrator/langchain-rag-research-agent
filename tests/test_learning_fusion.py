from types import SimpleNamespace
import pytest
from rag_research_agent.lab.retrieval_fusion import search
from scripts.compare_retrieval_fusion import compare


class DivergentLibrary:
    def __init__(self, path=None, embedder=None):
        self.chunks = [SimpleNamespace(document_id=s, safe_text=s, chunk_id=s) for s in ("a", "b", "c")]
        self.index = SimpleNamespace(close=lambda: None)

    def build(self, docs):
        return self

    def search(self, query, k, mode):
        order = [(0, .9), (1, .8), (2, .1)] if mode == "vector" else [(2, 3), (1, 1)]
        return [(self.chunks[i], score, rank) for rank, (i, score) in enumerate(order[:k], 1)]


def test_fusion_changes_ranking_and_alpha_endpoints():
    lib = DivergentLibrary()
    assert search(lib, "q", 3, "weighted", 0)[0][0].chunk_id == "c"
    assert search(lib, "q", 3, "weighted", 1)[0][0].chunk_id == "a"
    small = search(lib, "q", 3, "rrf", rrf_k=1)
    large = search(lib, "q", 3, "rrf", rrf_k=100)
    assert small[0][1] != large[0][1]
    assert {c.chunk_id for c, _, _ in small} == {"a", "b", "c"}
    with pytest.raises(ValueError):
        search(lib, "q", 3, "weighted", float("nan"))


def test_comparison_reports_types_and_keeps_confirm_out(tmp_path):
    import json
    path = tmp_path / "set.json"
    path.write_text(json.dumps({"name": "synthetic", "schema": "golden-retrieval/2", "items": [
        {"id": "q", "question": "q", "type": "paraphrase", "split": "compare", "answerable": True,
         "relevant": [{"source": "a", "quote": "a", "grade": 2}]},
        {"id": "held", "question": "held", "type": "off_topic", "split": "confirm", "answerable": False, "relevant": []}]}))
    result = compare(path, tmp_path / "out", alphas=[.5], rrf_ks=[10], library_factory=DivergentLibrary,
                     policy=None, corpus=[{"id": s, "title": s, "text": s} for s in ("a", "b", "c")])
    assert len(result) == 4
    assert all(set(r["result"]["by_split"]) == {"compare"} for r in result)
    assert "경로 시험" in (tmp_path / "out/fusion.md").read_text(encoding="utf-8")
