"""Real Chroma integration with small, caller-supplied vectors (no models)."""
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
from threading import Barrier

import pytest

from rag_research_agent.core.contracts import Chunk
from rag_research_agent.store import chroma_pointer
from rag_research_agent.store.chroma_pointer import ChromaPointer


@pytest.fixture
def store(tmp_path):
    return ChromaPointer(tmp_path)


def publish(store, label="alpha"):
    chunks = [Chunk("doc-a1", "chunk-a1", "source-a1", "synthetic",
                    "Synthetic", label, 1, "chunker-a1", "mask-a1", "policy-a1")]
    return store.publish(chunks, [[1.0, 0.0]], collection="pointer_test", dimension=2)


def assert_active(store, label):
    index = store.open_active()
    try:
        assert index.vector_count() == 1
        assert index.search_vector([1.0, 0.0], k=1)[0][0].safe_text == label
        assert index.search_lex(label)[0][0].chunk_id == "chunk-a1"
    finally:
        index.close()


def test_new_versions_reopen_and_old_reader_survives(store):
    assert publish(store) == "v1"
    original_manifest = (store.root / "versions/v1/manifest.json").read_bytes()
    old = store.open_active()
    try:
        assert publish(store, "beta") == "v2"
        assert old.search_vector([1.0, 0.0])[0][0].safe_text == "alpha"
        assert (store.root / "versions/v1/manifest.json").read_bytes() == original_manifest
        assert_active(ChromaPointer(store.root), "beta")
    finally:
        old.close()


def test_pointer_is_complete_before_atomic_replace(store, monkeypatch):
    publish(store)
    replace = chroma_pointer.os.replace
    calls = []

    def inspect(source, destination):
        assert Path(destination) == store.root / "current.json"
        assert Path(source).parent == store.root
        assert store.active_version() == "v1"
        assert json.loads(Path(source).read_text(encoding="utf-8")) == {
            "version": "v2", "previous": "v1"}
        candidate = store._open("v2")
        candidate.close()
        calls.append(destination)
        return replace(source, destination)

    monkeypatch.setattr(chroma_pointer.os, "replace", inspect)
    publish(store, "beta")
    assert len(calls) == 1
    assert store.active_version() == "v2"
    assert not list(store.root.glob(".current-*.tmp"))


def test_failed_replace_retains_pointer_and_reserved_version(store, monkeypatch):
    publish(store)
    before = (store.root / "current.json").read_bytes()
    with monkeypatch.context() as patch:
        def locked(*args):
            raise PermissionError("synthetic sharing violation")
        patch.setattr(chroma_pointer.os, "replace", locked)
        with pytest.raises(PermissionError):
            publish(store, "beta")
    assert (store.root / "current.json").read_bytes() == before
    assert (store.root / "versions/v2").is_dir()
    assert not list(store.root.glob(".current-*.tmp"))
    assert publish(store, "gamma") == "v3"
    assert_active(store, "gamma")


def test_rollback_only_changes_pointer_and_verifies_target(store, monkeypatch):
    publish(store)
    publish(store, "beta")

    def forbidden(*args, **kwargs):
        pytest.fail("version directories must not be deleted or moved")

    monkeypatch.setattr(chroma_pointer.shutil, "rmtree", forbidden)
    monkeypatch.setattr(chroma_pointer.shutil, "move", forbidden)
    assert store.rollback() == "v1"
    assert_active(store, "alpha")
    assert store.rollback() == "v2"
    assert store.activate("v2") == "v2"  # no-op preserves rollback target
    assert store.rollback() == "v1"
    with pytest.raises(FileNotFoundError):
        store.activate("v9")
    assert store.active_version() == "v1"


def test_prune_locked_retired_version_warns_and_continues(store, monkeypatch, caplog):
    for label in ("alpha", "beta", "gamma", "delta"):
        publish(store, label)
    remove = chroma_pointer.shutil.rmtree

    def locked(path):
        if path.name == "v1":
            raise PermissionError("synthetic sharing violation")
        return remove(path)

    with monkeypatch.context() as patch:
        patch.setattr(chroma_pointer.shutil, "rmtree", locked)
        assert store.prune() == {"removed": ["v2"], "kept_locked": ["v1"]}
    assert "CHROMA_PRUNE_LOCKED" in caplog.text
    assert "synthetic sharing violation" not in caplog.text
    assert (store.root / "versions/v3").is_dir()
    assert (store.root / "versions/v4").is_dir()
    assert store.prune() == {"removed": ["v1"], "kept_locked": []}
    assert_active(store, "delta")


def test_concurrent_readers_during_pointer_switches(store):
    publish(store)
    publish(store, "beta")
    barrier = Barrier(4)

    def reader():
        barrier.wait(timeout=15)
        observed = set()
        for _ in range(20):
            observed.add(ChromaPointer(store.root).active_version())
            index = store.open_active()
            try:
                assert index.vector_count() == 1
                assert index.search_vector([1.0, 0.0])[0][0].safe_text in {"alpha", "beta"}
            finally:
                index.close()
        return observed

    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(reader) for _ in range(3)]
        barrier.wait(timeout=15)
        for version in ("v1", "v2") * 4:
            store.activate(version)
        for future in futures:
            assert future.result() <= {"v1", "v2"}


def test_failed_build_never_activates_and_next_build_uses_fresh_folder(store):
    publish(store)
    with pytest.raises(ValueError, match="dimension mismatch"):
        store.publish([Chunk("doc-a1", "chunk-a1", "v1", "synthetic", "Title",
                             "alpha", 1, "ck-a1", "mask-a1", "policy-a1")],
                      [[1.0]], collection="pointer_test", dimension=2)
    assert store.active_version() == "v1"
    assert publish(store, "gamma") == "v3"
    with pytest.raises(FileNotFoundError):
        store.activate("v2")
    assert_active(store, "gamma")


def test_writer_exclusion_across_instances(store):
    publish(store)
    with store._writer():
        with pytest.raises(RuntimeError, match="CHROMA_WRITER_BUSY"):
            ChromaPointer(store.root).rollback()
    assert not (store.root / ".writer.lock").exists()
    with pytest.raises(ValueError, match="no previous"):
        store.rollback()


def test_pruning_highest_version_never_reuses_its_id(store):
    for label in ("alpha", "beta", "gamma"):
        publish(store, label)
    store.activate("v1")
    store.activate("v2")
    assert store.prune() == {"removed": ["v3"], "kept_locked": []}
    assert publish(store, "delta") == "v4"


@pytest.mark.parametrize("version", ["../v1", "v0", "v01", "v1/child", "other"])
def test_invalid_version_is_rejected(store, version):
    publish(store)
    with pytest.raises(ValueError, match="invalid Chroma version"):
        store.activate(version)
    assert store.active_version() == "v1"


def test_tampered_manifest_blocks_activation(store):
    publish(store)
    publish(store, "beta")
    manifest = store.root / "versions/v1/manifest.json"
    payload = json.loads(manifest.read_text(encoding="utf-8"))
    payload["chunks"][0]["safe_text"] = "tampered"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="content_hash"):
        store.rollback()
    assert store.active_version() == "v2"


@pytest.mark.parametrize("fail_add", [False, True])
def test_publisher_closes_real_writer_even_when_add_fails(store, monkeypatch, fail_add):
    from chromadb.api.models.Collection import Collection

    publish(store)
    factory = chroma_pointer._client
    opened, closed = [], []

    def track_client(path):
        client = factory(path)
        opened.append(client)
        close = client.close

        def track_close():
            close()
            closed.append(client)

        monkeypatch.setattr(client, "close", track_close)
        return client

    monkeypatch.setattr(chroma_pointer, "_client", track_client)
    if fail_add:
        def fail_write(*args, **kwargs):
            raise ValueError("synthetic add failure")

        with monkeypatch.context() as patch:
            patch.setattr(Collection, "add", fail_write)
            with pytest.raises(ValueError, match="synthetic add failure"):
                publish(store, "beta")
        assert store.active_version() == "v1"
        assert not (store.root / ".writer.lock").exists()
        assert (store.root / "versions/v2").is_dir()
        assert not (store.root / "versions/v2/manifest.json").exists()
    else:
        assert publish(store, "beta") == "v2"
        assert_active(store, "beta")
    assert len(opened) == 1
    assert len(closed) == 1
    assert closed[0] is opened[0]
