import json
from types import SimpleNamespace
import pytest
from rag_research_agent.embed.registry import create_embedder
from rag_research_agent.lab.learning_applications import duplicate_candidates, compress, injection_signal
from scripts.learning_applications import run


def test_candidates_are_pairwise_review_only_and_do_not_mutate():
    docs = [{"id": "a", "text": "same"}, {"id": "b", "text": "same"}, {"id": "c", "text": "other"}]
    before = json.dumps(docs)
    result = duplicate_candidates(docs, [[1,0], [1,0], [0,1]], .9)
    assert result["groups"] == [["a", "b"]]
    assert result["pairs"][0]["review"] == "PENDING_HUMAN_REVIEW"
    assert not result["merged"] and result["action"] == "REVIEW_ONLY"
    assert json.dumps(docs) == before
    with pytest.raises(ValueError):
        duplicate_candidates(docs[:2], [[1], [0]], .5)


def test_compression_keeps_protected_overflow_explicit():
    docs = [{"id": "a", "text": "합성 계약 자료를 반드시 보관한다. 다른 합성 문장이다."}]
    result = compress(docs, create_embedder("fake"), "계약 자료", 5, protected=["a"])
    assert result["mmr"]["status"] == "BUDGET_PROTECTED_OVERFLOW"
    assert result["mmr"]["chars"] > 5
    assert result["equalizer"]["mechanism"] != result["mmr"]["mechanism"]


def test_similarity_signal_cannot_override_canonical_block():
    class Block:
        def check(self, text):
            return SimpleNamespace(allowed=False, reason="canonical-block")
    result = injection_signal(create_embedder("fake"), "합성 계약서 질문", 1., Block())
    assert result["auxiliary_signal"]["decision"] == "ALLOW"
    assert result["canonical_guard"]["allowed"] is False
    assert not result["used_in_retrieval_quality_denominator"]


def test_small_applications_report_and_source_unchanged(tmp_path):
    source = tmp_path / "corpus.json"
    source.write_text(json.dumps([{"id": "a", "text": "합성 계약 자료다."}, {"id": "b", "text": "합성 계약 자료다."}]), encoding="utf-8")
    before = source.read_bytes()
    result = run(source, tmp_path / "out", policy=None)
    assert result["real_model"] is None
    assert result["path_test"]["duplicates"]["pairs"]
    assert source.read_bytes() == before
    text = (tmp_path / "out/applications.md").read_text(encoding="utf-8")
    assert "경로 시험" in text and "PENDING_HUMAN_REVIEW" in text
