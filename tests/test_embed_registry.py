import json
import os
from types import SimpleNamespace

import pytest
from test_library_incremental import fake_chroma
from rag_research_agent.embed.providers import EmbeddingError
from rag_research_agent.embed.registry import MODELS, create_embedder
from rag_research_agent.rag.library import Library
from rag_research_agent.core.contracts import RetrievalUnavailable


def test_registry_pins_prefixes_and_offline_loader(monkeypatch):
    monkeypatch.delenv("HF_HUB_OFFLINE", raising=False)
    calls = []
    def loader(model, **kw):
        calls.append((model, kw))
        return SimpleNamespace(tokenizer=lambda text, **kw: {"input_ids": [1]})
    e5 = create_embedder("e5", revision="a" * 40, loader=loader)
    bge = create_embedder("bge-m3", revision="b" * 40, loader=loader)
    assert os.environ["HF_HUB_OFFLINE"] == "1"
    assert e5.query_text("synthetic").startswith("Instruct:") and bge.query_text("synthetic") == "synthetic"
    assert all(kw["local_files_only"] and not kw["trust_remote_code"] for _, kw in calls)
    assert all(MODELS[k]["dimension"] == 1024 for k in ("e5", "bge-m3"))


def test_missing_cache_unpinned_revision_and_unknown_name(tmp_path):
    def missing(*a, **kw):
        raise OSError("synthetic cache miss")
    with pytest.raises(EmbeddingError, match="prepare_models"):
        create_embedder("e5", revision="a" * 40, loader=missing)
    for revision in ("main", "short", ""):
        with pytest.raises(EmbeddingError, match="revision"):
            create_embedder("e5", revision=revision, loader=missing)
    with pytest.raises(EmbeddingError, match="prepare_models"):
        create_embedder("e5", models_file=tmp_path / "missing.json")
    with pytest.raises(EmbeddingError, match="unknown"):
        create_embedder("unknown")


def test_library_string_identity_and_reopen_mismatch(tmp_path, fake_chroma):
    lib = Library(tmp_path, embedder="fake").build([("one", "title", "합성 문서다.")])
    data = json.loads((tmp_path / "library_manifest.json").read_text(encoding="utf-8"))
    assert "fake-char-bigram@fake-v1:256" == data["embedder"]
    other = create_embedder("fake")
    other.revision = "different"
    with pytest.raises(RetrievalUnavailable, match="built with"):
        Library(tmp_path, embedder=other).open()
