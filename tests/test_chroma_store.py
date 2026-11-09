"""Chroma adapter: same surface as the memvid index, local files only, telemetry off."""
import pytest

chromadb = pytest.importorskip("chromadb", reason="needs the `chroma` extra")  # explicit, reported skip

from rag_research_agent.core.contracts import Chunk, RetrievalUnavailable
from rag_research_agent.embed.providers import FakeEmbedder
from rag_research_agent.store.chroma_store import ChromaIndex, _client, publish_chroma

TEXTS = ["보증금 반환 요구는 해지 통보 뒤에 접수됐다", "누수의 실제 원인은 배관 공사였다", "손해액은 수리비에 한정된다"]


def chunks():
    return [Chunk(f"D{i}", f"D{i}:c01:v1", "v1", "synthetic", f"t{i}", t, len(t), "ck1", "m1", "p1")
            for i, t in enumerate(TEXTS)]


def build(tmp_path):
    emb = FakeEmbedder(dimension=64)
    cs = chunks()
    return publish_chroma(cs, emb.encode_documents([c.safe_text for c in cs]), path=tmp_path, collection="rra_test",
                          dimension=64), emb


def test_publish_verify_and_vector_search(tmp_path):
    idx, emb = build(tmp_path)
    hits = idx.search_vector(emb.encode_query(TEXTS[1]), k=3)
    assert hits[0][0].chunk_id == "D1:c01:v1" and hits[0][2] == 1
    assert idx.vector_count() == 3


def test_reopen_from_disk_and_lex_search(tmp_path):
    build(tmp_path)
    idx = ChromaIndex(tmp_path, "rra_test", chunks(), 64)
    idx.verify()
    assert idx.search_lex("배관 공사 원인")[0][0].chunk_id == "D1:c01:v1"
    assert idx.search_lex("") == []


def test_tampered_or_mismatched_index_is_refused(tmp_path):
    build(tmp_path)
    other = chunks()
    other[0] = Chunk("D0", "D0:c01:v1", "v1", "synthetic", "t0", "바뀐 본문", 4, "ck1", "m1", "p1")
    with pytest.raises(RetrievalUnavailable):
        ChromaIndex(tmp_path, "rra_test", other, 64).verify()
    with pytest.raises(RetrievalUnavailable):
        ChromaIndex(tmp_path, "rra_test", chunks(), 64).search_vector([0.0] * 8)


def test_telemetry_is_off(tmp_path):
    assert _client(tmp_path).get_settings().anonymized_telemetry is False
