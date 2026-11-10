import json
from types import SimpleNamespace

from rag_research_agent.embed.registry import create_embedder
from rag_research_agent.embed.providers import EmbeddingError
from rag_research_agent.observe.calibration import summarize_calibration
from scripts.compare_embedders import compare_models


def row(id, correct=True, score=0.7):
    return {"id": id, "type": "synthetic", "split": "compare", "expected": ["one"] if correct else [],
            "correct_score": score if correct else None, "wrong_score": 0.2,
            "vector": {"topk": ["one", "two"], "top1": score, "gap": 0.1}}


def test_calibration_boundary_cases():
    one = summarize_calibration([row("one")])
    assert one["tau_low"] == 0.7 and one["mrr"] == 1 and one["no_evidence_count"] == 0
    tied = summarize_calibration([row("one", score=0.5), row("negative", False, score=0.5)])
    assert tied["tau_high"] > 0.5 and tied["decision"]["no_evidence_passed"] == 0
    assert summarize_calibration([])["tau_high"] is None


class FakeIndexLibrary:
    """Injected deterministic index; production path still uses local Chroma."""
    def __init__(self, path, embedder):
        self.path, self.embedder = path, embedder
        self.index = SimpleNamespace(close=lambda: None)
    def build(self, docs):
        self.chunks = [SimpleNamespace(document_id=id, safe_text=text) for id, title, text in docs]
        self.vectors = self.embedder.encode_documents([c.safe_text for c in self.chunks])
        self.path.mkdir(parents=True)
        (self.path / "synthetic_index.json").write_text(json.dumps(self.vectors))
        return self
    def search(self, query, k, mode):
        q = self.embedder.encode_query(query)
        ranks = sorted(zip(self.chunks, self.vectors), key=lambda cv: -sum(a*b for a,b in zip(q, cv[1])))
        return [(c, sum(a*b for a,b in zip(q, v)), n) for n,(c,v) in enumerate(ranks[:k], 1)]


def test_fake_comparison_pipeline_and_unprepared_model(tmp_path):
    corpus, evidence, negative = [tmp_path / name for name in ("corpus.json", "gold.json", "negative.json")]
    corpus.write_text(json.dumps([{"id": "one", "title": "one", "text": "합성 금리 자료"}, {"id": "two", "title": "two", "text": "합성 계약 자료"}]))
    evidence.write_text(json.dumps([{"question": "합성 금리", "source": "one", "type": "paraphrase"}]))
    negative.write_text(json.dumps([{"question": "바다 날씨", "source": None, "type": "off_topic"}]))
    def factory(name):
        if name != "fake":
            raise EmbeddingError("unprepared synthetic model")
        return create_embedder("fake")
    results = compare_models(["fake", "e5"], evidence, negative, corpus, tmp_path / "out", factory, FakeIndexLibrary)
    assert results[0]["revision"] == "fake-v1" and results[1]["status"] == "미준비"
    assert (tmp_path / "out/calibration/fake.json").is_file()
    assert (tmp_path / "out/compare/comparison.html").is_file()
