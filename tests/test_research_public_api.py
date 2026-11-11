"""Exercise the facade through existing graph/filter/store implementations, offline."""
import os
from pathlib import Path
import re
import subprocess
import sys

import pytest

from rag_research_agent.rag import research_api as api


def test_public_exports_are_existing_objects():
    from rag_research_agent.guard import domain_filter
    from rag_research_agent.rag import research_graph, research_chroma

    assert api.API_VERSION == "0.1"
    for name in ("ResearchConfig", "ResearchResult", "SearchFn", "keyword_search"):
        assert getattr(api, name) is getattr(research_graph, name)
    for name in ("DomainFilter", "register", "get_filter"):
        assert getattr(api, name) is getattr(domain_filter, name)
    assert api.chroma_search is research_chroma.make_chroma_search
    namespace = {}
    exec("from rag_research_agent.rag.research_api import *", namespace)
    assert set(api.__all__) <= namespace.keys()
    with pytest.raises(AttributeError):
        getattr(api, "unknown_public_name")


@pytest.mark.parametrize("example", range(3))
def test_documented_examples_execute(example):
    root = Path(__file__).resolve().parents[1]
    doc = (root / "docs/RESEARCH_API.ko.md").read_text(encoding="utf-8")
    examples = re.findall(r"```python\n(.*?)```", doc, re.S)
    assert len(examples) == 3
    exec(compile(examples[example], f"RESEARCH_API.ko.md:example-{example}", "exec"), {})


def test_default_preserves_runner_result():
    from rag_research_agent.rag.research_graph import ResearchRunner

    search = api.keyword_search({"doc-a1": "주택 거래량은 18% 감소했다."})
    question = "주택 거래량을 정리해 주세요."
    assert api.run_research(question, search=search) == ResearchRunner(search).run(question)


def test_legal_blocks_before_search():
    from rag_research_agent.guard.legal_filter import LegalFilter

    # A fail-fast search callback proves that the real filter stops retrieval.
    def forbidden_search(query, k):
        pytest.fail("blocked input reached retrieval")

    assert isinstance(api.get_filter("legal"), LegalFilter)
    result = api.run_research(" ", search=forbidden_search, domain="legal")
    assert result.stopped == "BLOCKED" and result.sources == ()
    assert result.path == ("screen",)
    assert result.log == ("SCREEN:BLOCK:EMPTY_INPUT",)


def test_real_registered_filter_rejects_empty_evidence():
    from rag_research_agent.guard.legal_filter import LegalFilter
    from uuid import uuid4

    name = "legal-" + uuid4().hex
    api.register(name, LegalFilter)
    result = api.run_research("계약 내용을 정리해 주세요.", search=api.keyword_search({}), domain=name)
    assert result.stopped == "VERIFY_FAILED"
    assert "NO_EVIDENCE" in result.verify_codes
    assert not result.draft.body()
    assert result.report == result.draft.render()
    assert "VERIFY:FAIL:NO_EVIDENCE" in result.log


def test_unknown_domain_is_rejected():
    with pytest.raises(KeyError, match="unknown domain filter"):
        api.run_research("자료 정리", search=api.keyword_search({}), domain="unknown-r19")


def test_facade_import_without_optional_graph_dependencies():
    root = Path(__file__).resolve().parents[1]
    code = f"import sys; sys.path.insert(0, {str(root / 'src')!r})\n" + '''
import importlib.abc
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'langchain', 'langchain_core', 'langgraph',
                                      'langsmith', 'chromadb', 'memvid_sdk', 'sentence_transformers'}:
            raise ImportError('blocked optional dependency: ' + fullname)
sys.meta_path.insert(0, Block())
from rag_research_agent.rag.research_api import API_VERSION, DomainFilter, register, get_filter, run_research
assert API_VERSION == '0.1'
assert isinstance(get_filter('research'), DomainFilter)
assert 'rag_research_agent.rag.research_graph' not in sys.modules
'''
    # Do not inherit tracing/auth environment into the isolated import check.
    env = {key: os.environ[key] for key in ("SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP")
           if key in os.environ}
    result = subprocess.run([sys.executable, "-I", "-c", code], cwd=root,
                            env=env, capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
