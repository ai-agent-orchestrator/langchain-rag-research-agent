import pytest

from memvid_guardrail.core.contracts import (Chunk, Evidence, IndexManifest, RetrievalMode, RetrievalResult,
                             RetrievalStatus, RetrievalUnavailable, build_query)


def chunk(doc="GUIDE-001", n=1, text="합성 청크"):
    return Chunk(doc, f"{doc}:c{n:02d}:v1", "v1", "synthetic-guides-v1", "합성 제목", text, 10,
                 "chunker-v1", "mask-v1", "legal-2026-11-06-v1")


def manifest(*chunks):
    return IndexManifest("idx-1", "idx-1.mv2", "0" * 64, "synthetic-guides-v1", "e5", "rev", 1024,
                         "l2", "chunker-v1", "2026-11-06T00:00:00Z", chunks)


def test_query_contract_excludes_client_name_and_blank_step():
    assert build_query("CIVIL", "보증금", None) == "CIVIL\n보증금"
    assert build_query("CIVIL", "보증금", "절차") == "CIVIL\n보증금\n절차"


def test_chunk_hash_is_bound_to_text():
    item = chunk()
    assert len(item.content_hash) == 64
    with pytest.raises(ValueError):
        Chunk(**{**item.__dict__, "content_hash": "f" * 64})
    with pytest.raises(ValueError):
        chunk(text="   ")


def test_manifest_rejects_duplicates_and_checks_model_identity():
    with pytest.raises(ValueError):
        manifest(chunk(), chunk())
    m = manifest(chunk())
    assert m.chunk("GUIDE-001:c01:v1").document_id == "GUIDE-001"
    assert m.accepts("e5", "rev", 1024, "l2")
    assert not m.accepts("e5", "other-rev", 1024, "l2")
    assert not m.accepts("e5", "rev", 768, "l2")


def test_status_and_evidence_must_agree():
    ev = Evidence(chunk(), RetrievalMode.VECTOR, 0.9, 1, "idx-1")
    RetrievalResult(RetrievalStatus.OK, RetrievalMode.VECTOR, "idx-1", (ev,))
    with pytest.raises(ValueError):
        RetrievalResult(RetrievalStatus.OK, RetrievalMode.VECTOR, "idx-1")
    with pytest.raises(ValueError):
        RetrievalResult(RetrievalStatus.BELOW_THRESHOLD, RetrievalMode.VECTOR, "idx-1", (ev,))
    with pytest.raises(ValueError):
        RetrievalResult(RetrievalStatus.OK, RetrievalMode.VECTOR, "idx-2", (ev,))
    with pytest.raises(ValueError):
        RetrievalResult(RetrievalStatus.OK, RetrievalMode.LEX, "idx-1", (ev,))


def test_document_ids_are_distinct_in_rank_order_and_citations_are_subset():
    evs = (Evidence(chunk("GUIDE-002", 1), RetrievalMode.VECTOR, 0.9, 1, "idx-1"),
           Evidence(chunk("GUIDE-002", 2), RetrievalMode.VECTOR, 0.8, 2, "idx-1"),
           Evidence(chunk("GUIDE-001", 1), RetrievalMode.VECTOR, 0.7, 3, "idx-1"),
           Evidence(chunk("GUIDE-005", 1), RetrievalMode.VECTOR, 0.6, 4, "idx-1"),
           Evidence(chunk("GUIDE-009", 1), RetrievalMode.VECTOR, 0.5, 5, "idx-1"))
    result = RetrievalResult(RetrievalStatus.OK, RetrievalMode.VECTOR, "idx-1", evs)
    assert result.document_ids() == ("GUIDE-002", "GUIDE-001", "GUIDE-005")
    assert result.cited_subset(["GUIDE-002:c01:v1"])
    assert not result.cited_subset(["GUIDE-003:c01:v1"])


def test_retrieval_failure_has_its_own_code():
    assert RetrievalUnavailable.code == "RETRIEVAL_UNAVAILABLE"
