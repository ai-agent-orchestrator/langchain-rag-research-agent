import pytest

from rag_research_agent.core.contracts import Chunk
from rag_research_agent.store import chroma_store
from rag_research_agent.store.retry import retry_io, transient_write_error


def test_exponential_delays_and_original_return():
    calls, delays, events = [], [], []
    def work():
        calls.append(1)
        if len(calls) <= 2:
            raise PermissionError("synthetic lock")
        return "result"
    assert retry_io(work, sleep=delays.append, on_retry=lambda *a: events.append(a)) == "result"
    assert delays == [0.2, 0.4] and len(events) == 2


def test_exhaustion_and_unrelated_error_preserve_identity():
    error = PermissionError("persistent")
    def work():
        raise error
    with pytest.raises(PermissionError) as caught:
        retry_io(work, sleep=lambda _: None)
    assert caught.value is error
    calls = []
    def invalid():
        calls.append(1)
        raise ValueError("not IO")
    with pytest.raises(ValueError):
        retry_io(invalid, sleep=lambda _: None)
    assert calls == [1]
    assert transient_write_error(RuntimeError("Tantivy error: An IO error occurred: os error 5"))
    assert not transient_write_error(RuntimeError("invalid schema"))


def test_chroma_write_paths_retry_with_injected_locks(monkeypatch, tmp_path):
    calls, contents = {}, {}
    def locked_once(key):
        calls[key] = calls.get(key, 0) + 1
        if calls[key] == 1:
            raise PermissionError("synthetic lock")
    class Collection:
        def add(self, ids, embeddings, documents, metadatas):
            locked_once("add")
            contents.update(zip(ids, metadatas))
        def get(self, ids, include):
            return {"ids": list(contents), "metadatas": list(contents.values())}
    col = Collection()
    class Client:
        def delete_collection(self, name):
            locked_once("delete")
        def create_collection(self, *a, **k):
            locked_once("create")
            return col
        def get_collection(self, name):
            return col
    monkeypatch.setattr(chroma_store, "_client", lambda _: Client())
    monkeypatch.setattr(chroma_store, "retry_io", lambda fn: retry_io(fn, sleep=lambda _: None))
    chunk = Chunk("SYNTH", "SYNTH:c01:v1", "v1", "synthetic", "title", "synthetic", 9, "v1", "m1", "p1")
    chroma_store.publish_chroma([chunk], [[1.0]], path=tmp_path, collection="synthetic", dimension=1)
    assert calls == {"delete": 2, "create": 2, "add": 2}
