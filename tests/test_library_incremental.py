from types import SimpleNamespace
import pytest

from rag_research_agent.core.contracts import RetrievalUnavailable
from rag_research_agent.rag import library
from rag_research_agent.store import chroma_store


@pytest.fixture
def fake_chroma(monkeypatch):
    collections = {}
    class Collection:
        def __init__(self):
            self.rows = {}
        def add(self, ids, embeddings, documents, metadatas):
            for cid, meta in zip(ids, metadatas):
                if cid in self.rows:
                    raise ValueError("duplicate")
                self.rows[cid] = meta
        def delete(self, ids):
            for cid in ids:
                self.rows.pop(cid, None)
        def get(self, ids=None, include=()):
            selected = [cid for cid in (ids if ids is not None else self.rows) if cid in self.rows]
            return {"ids": selected, "metadatas": [self.rows[cid] for cid in selected]}
    class Client:
        def delete_collection(self, name):
            collections.pop(name, None)
        def create_collection(self, name, **kwargs):
            collections[name] = Collection()
            return collections[name]
        def get_collection(self, name):
            return collections[name]
    client = Client()
    monkeypatch.setattr(chroma_store, "_client", lambda _: client)
    monkeypatch.setattr(library, "load_chroma", lambda: (SimpleNamespace(PersistentClient=lambda **kw: client), lambda **kw: None))
    return collections


def test_incremental_lifecycle_and_reopen(tmp_path, fake_chroma):
    lib = library.Library(tmp_path)
    assert lib.add([("one", "first", "합성 금리 비용 자료다.")]) == {"added": 1, "replaced": 0, "skipped": 0}
    assert lib.add([("one", "first", "합성 금리 비용 자료다.")])["skipped"] == 1
    assert lib.add([("one", "first", "합성 시장 부채 자료다."), ("two", "second", "합성 계약 자료다.")]) == {"added": 1, "replaced": 1, "skipped": 0}
    assert lib.search("부채", mode="lex")[0][0].document_id == "one"
    assert lib.remove("one") is True
    reopened = library.Library(tmp_path).open()
    assert [d["doc_id"] for d in reopened.documents()] == ["two"]
    assert reopened.search("부채", mode="lex") == []
    assert reopened.search("계약", mode="lex")[0][0].document_id == "two"
    assert reopened.remove("two") and reopened.search("계약") == []
    assert library.Library(tmp_path).open().documents() == []


def test_manifest_collection_drift_is_refused(tmp_path, fake_chroma):
    lib = library.Library(tmp_path).build([("one", "first", "합성 문서다.")])
    fake_chroma[lib.collection].rows["unexpected"] = {"content_hash": "bad"}
    with pytest.raises(RetrievalUnavailable, match="IDs differ"):
        lib.verify()


def test_real_chroma_incremental_when_installed(tmp_path):
    pytest.importorskip("chromadb", reason="needs the chroma extra for real incremental integration")
    lib = library.Library(tmp_path).build([("one", "first", "합성 금리 자료다.")])
    lib.add([("two", "second", "합성 계약 자료다.")])
    lib.remove("one")
    assert library.Library(tmp_path).open().search("계약", mode="lex")
