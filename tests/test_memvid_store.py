"""B02 memvid index with synthetic/fake vectors. Needs memvid-sdk; fails (never skips) without it."""
from pathlib import Path
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic_guides"

import json
import math
import random
import socket

import pytest

from memvid_guardrail.ingest.chunking import build_chunks, load_guides
from memvid_guardrail.embed.providers import FakeEmbedder
from memvid_guardrail.retrieve.gate import RelevanceRule, to_result
from memvid_guardrail.retrieve.keyword import lex_terms
from memvid_guardrail.store.memvid_store import load_memvid, open_active, publish_index
from memvid_guardrail.core.contracts import Chunk, RetrievalMode, RetrievalStatus, RetrievalUnavailable

pytestmark = pytest.mark.memvid
EMB = FakeEmbedder()
IDENTITY = dict(embedding_model=EMB.model_id, pinned_revision=EMB.revision, dimension=1024)


@pytest.fixture
def no_network(monkeypatch):
    attempts = []

    def refuse(self, address, *a, **k):
        attempts.append(address)
        raise OSError("blocked")
    monkeypatch.setattr(socket.socket, "connect", refuse)
    return attempts


@pytest.fixture
def published(tmp_path, no_network):
    chunks = build_chunks(load_guides(FIXTURE), EMB.count_tokens, "fake")
    vectors = EMB.encode_documents([c.safe_text for c in chunks])
    manifest = publish_index(chunks, vectors, index_dir=tmp_path, index_version="fake-v1", **IDENTITY)
    return tmp_path, manifest, chunks, vectors


def test_telemetry_is_forced_off():
    assert not load_memvid().is_telemetry_enabled()


def test_publish_verifies_every_chunk_and_activates_pointer(published, no_network):
    index_dir, manifest, chunks, vectors = published
    pointer = json.loads((index_dir / "active.json").read_text(encoding="utf-8"))
    assert pointer["indexVersion"] == "fake-v1" and pointer["sha256"] == manifest.sha256
    index = open_active(index_dir, **IDENTITY)
    try:
        assert index.vector_count(vectors[0]) == len(chunks)
        top = index.search_vector(vectors[-1], k=1)
        assert top[0][0].chunk_id == chunks[-1].chunk_id
        assert top[0][0].safe_text == chunks[-1].safe_text  # text comes from our manifest
        assert index.search_lex("CIVIL\n보증금 반환이 늦어요", k=3)
    finally:
        index.close()
    assert no_network == []


def test_many_chunks_survive_batched_writes(tmp_path):
    # Regression for memvid-sdk 2.0.160 dropping vectors from large put_many calls.
    rng = random.Random(3)
    chunks, vectors = [], []
    for i in range(60):
        vec = [rng.gauss(0, 1) for _ in range(1024)]
        norm = math.sqrt(sum(x * x for x in vec))
        vectors.append([x / norm for x in vec])
        chunks.append(Chunk(f"DOC-{i:03d}", f"DOC-{i:03d}:c01:v1", "v1", "synthetic", "제목", f"본문 {i}", 5,
                            "chunker", "mask", "policy"))
    publish_index(chunks, vectors, index_dir=tmp_path, index_version="batch-v1", **IDENTITY)
    index = open_active(tmp_path, **IDENTITY)
    try:
        assert index.vector_count(vectors[0]) == 60
    finally:
        index.close()


def test_versions_are_immutable(published):
    index_dir, _, chunks, vectors = published
    with pytest.raises(FileExistsError):
        publish_index(chunks, vectors, index_dir=index_dir, index_version="fake-v1", **IDENTITY)


def test_tampered_file_and_wrong_embedder_are_refused(published):
    index_dir, manifest, _, _ = published
    with pytest.raises(RetrievalUnavailable):
        open_active(index_dir, embedding_model="e5", pinned_revision="x", dimension=1024)
    with pytest.raises(RetrievalUnavailable):
        open_active(index_dir, **{**IDENTITY, "dimension": 768})
    (index_dir / manifest.file).write_bytes(b"tampered")
    with pytest.raises(RetrievalUnavailable):
        open_active(index_dir, **IDENTITY)


def test_missing_pointer_is_unavailable_not_empty(tmp_path):
    with pytest.raises(RetrievalUnavailable):
        open_active(tmp_path, **IDENTITY)


def test_lex_terms_drop_labels_masks_and_operators():
    assert lex_terms("CIVIL\n보증금 반환이 OR [PHONE] 늦어요!") == ["보증금", "반환이", "늦어요"]


def test_gate_statuses(published):
    index_dir, _, chunks, vectors = published
    index = open_active(index_dir, **IDENTITY)
    try:
        hits = index.search_vector(vectors[0], k=10)
    finally:
        index.close()
    strict = RelevanceRule(RetrievalMode.VECTOR, tau_abs=2.0, tau_gap=0.0, version="t")
    loose = RelevanceRule(RetrievalMode.VECTOR, tau_abs=0.0, tau_gap=0.0, version="t")
    assert to_result([], loose, "fake-v1").status == RetrievalStatus.EMPTY
    assert to_result(hits, strict, "fake-v1").status == RetrievalStatus.BELOW_THRESHOLD
    ok = to_result(hits, loose, "fake-v1")
    assert ok.status == RetrievalStatus.OK and ok.document_ids(3)[0] == chunks[0].document_id
