"""Index lifecycle: previous pointer, rollback with re-checks, prune keeps active + previous."""
from pathlib import Path

import pytest

from memvid_guardrail.core.contracts import RetrievalUnavailable
from memvid_guardrail.embed.providers import FakeEmbedder
from memvid_guardrail.ingest.chunking import build_chunks, load_guides
from memvid_guardrail.store.memvid_store import (activate, list_versions, open_active, prune,
                                                 publish_index)

pytestmark = pytest.mark.memvid
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "synthetic_guides"
EMB = FakeEmbedder()
IDENTITY = dict(embedding_model=EMB.model_id, pinned_revision=EMB.revision, dimension=1024)


@pytest.fixture(scope="module")
def corpus():
    chunks = build_chunks(load_guides(FIXTURE), EMB.count_tokens, "fake")[:10]
    return chunks, EMB.encode_documents([c.safe_text for c in chunks])


def states(index_dir):
    return {v["indexVersion"]: v["state"] for v in list_versions(index_dir)}


def test_versions_rollback_and_prune(tmp_path, corpus):
    chunks, vectors = corpus
    for version in ("v1", "v2", "v3"):
        publish_index(chunks, vectors, index_dir=tmp_path, index_version=version, **IDENTITY)
    assert states(tmp_path) == {"v1": "retired", "v2": "previous", "v3": "active"}

    activate(tmp_path, "v2", **IDENTITY)  # rollback
    assert states(tmp_path) == {"v1": "retired", "v2": "active", "v3": "previous"}
    index = open_active(tmp_path, **IDENTITY)
    try:
        assert index.manifest.index_version == "v2"
    finally:
        index.close()

    report = prune(tmp_path)
    assert report == {"removed": ["v1"], "kept_locked": []}
    assert not (tmp_path / "v1.mv2").exists() and states(tmp_path) == {"v2": "active", "v3": "previous"}


def test_activate_refuses_tampered_or_mismatched_versions(tmp_path, corpus):
    chunks, vectors = corpus
    publish_index(chunks, vectors, index_dir=tmp_path, index_version="v1", **IDENTITY)
    publish_index(chunks, vectors, index_dir=tmp_path, index_version="v2", **IDENTITY)
    with pytest.raises(RetrievalUnavailable):
        activate(tmp_path, "v1", **{**IDENTITY, "pinned_revision": "other"})
    with (tmp_path / "v1.mv2").open("ab") as handle:
        handle.write(b"tamper")
    with pytest.raises(RetrievalUnavailable):
        activate(tmp_path, "v1", **IDENTITY)
    with pytest.raises(RetrievalUnavailable):
        activate(tmp_path, "missing", **IDENTITY)
    assert states(tmp_path)["v2"] == "active"  # failed checks never move the pointer
