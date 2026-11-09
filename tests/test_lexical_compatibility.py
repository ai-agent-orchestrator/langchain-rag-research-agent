"""Keep the old public import and the store bound to the shared implementation."""
from rag_research_agent.core.lexical import lex_terms
from rag_research_agent.retrieve.keyword import lex_terms as legacy_lex_terms
from rag_research_agent.store.memvid_store import lex_terms as store_lex_terms


def test_legacy_import_and_store_use_the_shared_core_function():
    assert legacy_lex_terms is lex_terms
    assert store_lex_terms is lex_terms
