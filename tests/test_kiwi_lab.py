from types import SimpleNamespace
import pytest

from rag_research_agent.lab.kiwi_terms import kiwi_terms
from scripts.compare_lex_terms import compare


def test_fake_tokens_keep_stems_units_and_exclusions():
    tokens = [("CIVIL", "SL"), ("반환", "NNG"), ("이", "JKS"), ("계약서", "NNG"), ("를", "JKO"),
              ("OR", "SL"), ("가", "NNG"), ("10", "SN"), ("원", "NNB"), ("확인", "VV")]
    analyzer = SimpleNamespace(tokenize=lambda q: [SimpleNamespace(form=f, tag=t) for f,t in tokens])
    assert kiwi_terms("synthetic", analyzer) == ["반환", "계약서", "10원", "확인"]


def test_injected_term_comparison():
    class Index:
        def search_lex(self, query, k):
            return [(SimpleNamespace(document_id="one"), 1.0, 1)] if query == "반환" else []
    items = [{"question": "반환이", "source": "one", "type": "paraphrase"}]
    result = compare(items, Index(), {"lex": lambda q: [q], "kiwi": lambda q: ["반환"]})
    assert result["lex"]["mrr"] == 0 and result["kiwi"]["mrr"] == 1


def test_real_kiwi_particles_when_available():
    pytest.importorskip("kiwipiepy", reason="needs optional kiwi extra; installation is owner-run")
    assert "반환" in kiwi_terms("반환이 필요하다")
    assert "계약서" in kiwi_terms("계약서를 확인한다")
