"""Path tests only: real persistent Chroma and research graph, synthetic embeddings."""
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest

from rag_research_agent.core.contracts import Chunk, RetrievalMode
from rag_research_agent.core.research import span_matches
from rag_research_agent.embed.providers import EmbeddingError, FakeEmbedder
from rag_research_agent.guard.masking import mask_pii
from rag_research_agent.rag.research_chroma import make_chroma_search
from rag_research_agent.rag.research_graph import ResearchConfig, ResearchRunner
from rag_research_agent.retrieve.gate import RelevanceRule
from rag_research_agent.store.chroma_store import publish_chroma


TEXT = "주택 거래량은 18% 감소했다. 연락처는 010-0000-0000이다."
OTHER = "배관 공사의 누수 원인을 확인했다."


@pytest.fixture
def build():
    # Keep all persistent test output under .runs, including on the owner's PC.
    root = Path(".runs/r5/chroma-tests") / uuid4().hex
    indexes = []

    def create(texts=(TEXT, OTHER), document_ids=None):
        embedder = FakeEmbedder(dimension=64)
        chunks = [Chunk(document_ids[i] if document_ids else f"doc-a{i}", f"chunk-a{i}",
                        "v1", "synthetic", "Synthetic", text, embedder.count_tokens(text),
                        "ck1", "m1", "p1") for i, text in enumerate(texts)]
        index = publish_chroma(chunks, embedder.encode_documents(texts),
                               path=root / f"index-a{len(indexes)}", collection="research-test",
                               dimension=embedder.dimension)
        indexes.append(index)
        return index, embedder, chunks

    yield create
    for index in indexes:
        index.close()


def gate(absolute=0.5, gap=0.0):
    return RelevanceRule(RetrievalMode.VECTOR, absolute, gap, "synthetic-rule")


def test_result_shape_k_and_chunk_ids(build):
    index, embedder, chunks = build()
    search = make_chroma_search(index, embedder)
    assert search(TEXT, 1) == [(chunks[0].chunk_id, TEXT)]
    hits = search(TEXT, 8)
    assert hits == [(c.chunk_id, c.safe_text) for c in chunks]
    assert search(TEXT, 2) == hits
    assert index.vector_count() == 2  # adapter does not close the caller's index


@pytest.mark.parametrize("k", [0, -1])
def test_nonpositive_k_returns_empty(build, k):
    index, embedder, _ = build()
    assert make_chroma_search(index, embedder)(TEXT, k) == []


@pytest.mark.parametrize("k", [True, 1.5, "two"])
def test_noninteger_k_is_rejected(build, k):
    index, embedder, _ = build()
    with pytest.raises(ValueError, match="integer"):
        make_chroma_search(index, embedder)(TEXT, k)


def test_empty_collection(build):
    index, embedder, chunks = build()
    index._col.delete(ids=[c.chunk_id for c in chunks])
    assert make_chroma_search(index, embedder)(TEXT, 2) == []
    assert make_chroma_search(index, embedder, rule=gate())(TEXT, 2) == []


def test_absolute_gate_rejects_and_accepts(build):
    index, embedder, chunks = build()
    assert make_chroma_search(index, embedder, rule=gate(absolute=1.1))(TEXT, 1) == []
    assert make_chroma_search(index, embedder, rule=gate())(TEXT, 1) == [(chunks[0].chunk_id, TEXT)]


def test_gap_gate_sees_second_document_even_for_k_one(build):
    index, embedder, _ = build(texts=(TEXT, TEXT))
    search = make_chroma_search(index, embedder, rule=gate(gap=0.1))
    assert search(TEXT, 1) == []
    assert search(TEXT, 8) == []


def test_gate_looks_past_multiple_chunks_of_one_document(build):
    index, embedder, _ = build(texts=(TEXT, TEXT, TEXT),
                               document_ids=("doc-a", "doc-a", "doc-b"))
    assert make_chroma_search(index, embedder, rule=gate(gap=0.1))(TEXT, 1) == []


def test_gate_compares_documents_rather_than_chunks(build):
    index, embedder, chunks = build(texts=(TEXT, TEXT), document_ids=("doc-a", "doc-a"))
    hits = make_chroma_search(index, embedder, rule=gate(gap=0.1))(TEXT, 2)
    assert {sid for sid, _ in hits} == {c.chunk_id for c in chunks}


class PatternMasker:
    """Inject the existing frozen synthetic masker without copying its rules."""
    def mask(self, text):
        return mask_pii(text)


def test_masker_applies_to_query_and_retrieved_text(build):
    # Two distinguishable real vectors let the chosen result prove query masking.
    raw = "010-0000-0000"
    safe = mask_pii(raw)
    index, embedder, chunks = build(texts=(raw, safe))
    assert make_chroma_search(index, embedder)(raw, 1) == [(chunks[0].chunk_id, raw)]
    assert make_chroma_search(index, embedder, masker=PatternMasker())(raw, 1) == [
        (chunks[1].chunk_id, safe)]
    hits = make_chroma_search(index, embedder, masker=PatternMasker())(raw, 2)
    assert all(text == safe for _, text in hits)
    assert [c.safe_text for c in chunks] == [raw, safe]


def test_dimension_mismatch_rejected(build):
    index, _, _ = build()
    with pytest.raises(ValueError, match="dimensions"):
        make_chroma_search(index, FakeEmbedder(dimension=8))


@pytest.mark.parametrize("rule", [replace(gate(), mode=RetrievalMode.LEX),
                                  gate(absolute=float("nan")), gate(gap=float("inf"))])
def test_invalid_gate_rejected(build, rule):
    index, embedder, _ = build()
    with pytest.raises(ValueError, match="vector relevance rule"):
        make_chroma_search(index, embedder, rule=rule)


def test_embedding_error_propagates(build):
    index, embedder, _ = build()
    with pytest.raises(EmbeddingError, match="L2-normalized"):
        make_chroma_search(index, embedder)("", 1)


def test_research_runner_reaches_verified_masked_report(build):
    index, embedder, chunks = build(texts=(TEXT,))
    search = make_chroma_search(index, embedder, rule=gate(absolute=0.0), masker=PatternMasker())
    cfg = ResearchConfig(k=1, stance_split=False, auto_metrics=False)
    result = ResearchRunner(search, cfg).run("주택 거래량을 정리해 주세요.", ("주택 거래량",))
    assert result.verify_codes == ()
    assert result.path[-1] == "verify"
    assert "18%" in result.report
    assert "010-0000-0000" not in result.report
    assert result.sources[0].text == mask_pii(TEXT)
    assert result.sources[0].source_id == chunks[0].chunk_id
    assert result.claims and all(s.claim_ids for s in result.draft.sentences if not s.note)
    assert all(span_matches(c, {s.source_id: s for s in result.sources}) for c in result.claims)


def test_rejected_gate_leaves_runner_without_claims(build):
    index, embedder, _ = build()
    search = make_chroma_search(index, embedder, rule=gate(absolute=1.1))
    cfg = ResearchConfig(k=1, stance_split=False, auto_metrics=False,
                         gap_loop=False, rewrite_loop=False)
    result = ResearchRunner(search, cfg).run(TEXT, ("주택 거래량",))
    assert result.sources == () and result.claims == ()
    assert result.verify_codes == ("EMPTY_REPORT",)
