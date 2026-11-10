import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from rag_research_agent.core.types import Status
from rag_research_agent.embed.registry import create_embedder
from rag_research_agent.observe.golden_v2 import load, score_item
from rag_research_agent.rag.query_rewrite import rewrite_queries
from rag_research_agent.rag.retry_graph import build_graph

ROOT = Path(__file__).resolve().parents[1]


class MemoryLibrary:
    def __init__(self, corpus):
        self.embedder = create_embedder("fake")
        self.chunks = [SimpleNamespace(chunk_id=a["id"] + ":c01", document_id=a["id"], safe_text=a["text"]) for a in corpus]
        self.vectors = self.embedder.encode_documents([c.safe_text for c in self.chunks])
    def search(self, query, k, mode):
        q = self.embedder.encode_query(query)
        scored = [(c, sum(x*y for x,y in zip(q,v))) for c,v in zip(self.chunks,self.vectors)]
        scored.sort(key=lambda item: (-item[1], item[0].chunk_id))
        return [(c, score, rank) for rank, (c, score) in enumerate(scored[:k], 1)]


def test_deterministic_query_variants():
    variants = rewrite_queries("2026년 반환 그리고 계약서, 3개월 자료")
    assert {v["reason"] for v in variants} >= {"subquestion", "without_numeric_period"}
    assert len({v["query"] for v in variants}) == len(variants)
    assert any("2026" not in v["query"] for v in variants if v["reason"] == "without_numeric_period")


def test_retry_eventually_succeeds_and_reuses_equalizer_stages():
    chunk = SimpleNamespace(chunk_id="one:c01", document_id="one", safe_text="핵심은 비용이다.")
    class Library:
        chunks = [chunk]
        def search(self, query, k, mode):
            return [(chunk, 0.1 if "그리고" in query else 0.9, 1)]
    graph = build_graph(Library(), tau=0.5)
    result = graph.invoke({"query": "비용 그리고 자료"})
    assert len(result["attempts"]) == 2 and result["status"] == Status.OK
    assert result["final_prompt_input"] and "compose_and_check" in result["node_calls"]
    assert result["generation_calls"] == 0


def test_no_evidence_requests_more_and_loop_is_bounded():
    corpus = json.loads((ROOT / "data/articles.json").read_text(encoding="utf-8"))
    graph = build_graph(MemoryLibrary(corpus), tau=1.0)
    for item in json.loads((ROOT / "data/golden_no_evidence.json").read_text(encoding="utf-8")):
        result = graph.invoke({"query": item["question"]})
        assert result["status"] == Status.REQUEST_MORE and len(result["attempts"]) <= 3
        assert result["generation_calls"] == 0 and result["final_prompt_input"] == ""
    with pytest.raises(ValueError):
        build_graph(MemoryLibrary(corpus), max_retries=3)


def test_multihop_comparison_recall_before_after(tmp_path):
    dataset = load(ROOT / "data/golden_retrieval/terms_v2.json")
    library = MemoryLibrary(dataset["corpus"])
    graph = build_graph(library, tau=1.0)
    metrics = []
    for item in dataset["items"]:
        if item["type"] not in ("multi_hop", "comparison"):
            continue
        result = graph.invoke({"query": item["question"]})
        before = library.search(item["question"], 3, "vector")
        convert = lambda hits: [{"source": c.document_id, "text": c.safe_text} for c, _, _ in hits]
        a, b = score_item(item, convert(before), k=3), score_item(item, convert(result["hits"]), k=3)
        metrics.append({"id": item["id"], "type": item["type"], "before": a["recall"], "after": b["recall"], "attempts": len(result["attempts"])})
        assert len(result["attempts"]) <= 3
    assert metrics
    (tmp_path / "e2-recall.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
