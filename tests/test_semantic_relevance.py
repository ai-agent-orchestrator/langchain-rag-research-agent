import hashlib
import pytest

from rag_research_agent.rag.brief import Parts, build_brief
from rag_research_agent.retrieve.semantic_relevance import make_semantic_relevance


class Fake:
    def __init__(self):
        self.queries = self.documents = 0

    def vector(self, text):
        v = [0.0] * 128
        for word in text.split():
            v[int.from_bytes(hashlib.sha256(word.encode()).digest()[:2]) % len(v)] += 1
        return v

    def encode_query(self, text):
        self.queries += 1
        return self.vector(text)

    def encode_documents(self, texts):
        self.documents += 1
        return [self.vector(t) for t in texts]


def test_related_scores_and_cached_repeats():
    fake = Fake()
    relevance = make_semantic_relevance(fake)
    score = relevance("금리 비용")
    assert score("금리 비용") > score("날씨 바다")
    assert 0 <= score("날씨 바다") <= 1
    score("금리 비용")
    relevance("금리 비용")("금리 비용")
    assert (fake.queries, fake.documents) == (1, 2)


def test_empty_task_none_normalization_and_cache_off():
    fake = Fake()
    assert make_semantic_relevance(fake)(None)("anything") == 1
    assert fake.queries == 0
    score = make_semantic_relevance(fake, normalize="none", cache=False)("금리")
    assert score("금리") == 1 and score("금리") == 1
    assert fake.documents == 2
    with pytest.raises(ValueError):
        make_semantic_relevance(fake, normalize="unknown")


def test_parts_integration_without_model_download():
    brief, trace = build_brief("금리 비용. 날씨 바다.", task="금리", parts=Parts(relevance=make_semantic_relevance(Fake())))
    assert trace.rows and all(0 <= r["relevance"] <= 1 for r in trace.rows)
    assert brief.versions["rule_version"]
