from types import SimpleNamespace
import pytest

from rag_research_agent.rag.lc_adapters import LibraryRetriever, EqualizerRunnable, library_brief_tool, make_research_chain
from rag_research_agent.rag.profile import Equalizer


class FakeLibrary:
    def search(self, query, k=8, mode="hybrid"):
        chunk = SimpleNamespace(chunk_id="synthetic:c01:v1", document_id="synthetic", title="합성", safe_text="핵심은 비용이다. 다만 위험은 확인되지 않았다.")
        return [(chunk, 0.8, 1)]
    def brief(self, query, profile="research"):
        hits = self.search(query)
        brief, trace = Equalizer.from_profile(profile).brief(hits[0][0].safe_text, task=query)
        return brief, trace, hits


def test_retriever_documents_preserve_provenance():
    docs = LibraryRetriever(library=FakeLibrary(), k=2).invoke("비용")
    assert docs[0].page_content.startswith("핵심은")
    assert docs[0].metadata == {"chunk_id": "synthetic:c01:v1", "document_id": "synthetic", "title": "합성", "score": 0.8, "rank": 1}


@pytest.mark.parametrize("value", ["핵심은 비용이다.", {"text": "핵심은 비용이다.", "task": "비용"}])
def test_runnable_string_and_dict(value):
    result = EqualizerRunnable().invoke(value)
    assert result["status"] == "OK" and result["kept_ids"] and isinstance(result["brief"], str)


def test_tool_and_lcel_chain_reuse_public_library_calls():
    library = FakeLibrary()
    tool = library_brief_tool(library)
    assert tool.name == "research_brief"
    assert isinstance(tool.invoke({"question": "비용"}), str)
    assert make_research_chain(library).invoke("비용")["kept_ids"]


def test_real_fake_embedder_library_when_chroma_available(tmp_path):
    pytest.importorskip("chromadb", reason="needs chroma extra for persisted fake-embedder library integration")
    from rag_research_agent.rag.library import Library
    lib = Library(tmp_path, embedder="fake").build([("one", "합성", "핵심은 비용이다.")])
    assert LibraryRetriever(library=lib).invoke("비용")
