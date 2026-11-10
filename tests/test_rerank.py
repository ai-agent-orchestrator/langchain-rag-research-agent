import pytest

from rag_research_agent.core.contracts import Chunk
from rag_research_agent.retrieve.rerank import (
    IdentityReranker,
    LexicalOverlapReranker,
    Reranker,
)


def chunk(chunk_id, text, title="title"):
    return Chunk(
        document_id="doc", chunk_id=chunk_id, source_version="v1",
        collection_id="collection", title=title, safe_text=text,
        token_count=len(text.split()), chunker_version="v1",
        masking_version="v1", policy_version="v1",
    )


def test_identity_preserves_order_objects_duplicates_and_input():
    a, b = chunk("a", "unrelated"), chunk("b", "contract payment")
    chunks = [a, b, a]
    reranker: Reranker = IdentityReranker()
    result = reranker.rerank("contract payment", chunks)
    assert result == [(a, 1.0), (b, 0.5), (a, 0.0)]
    assert all(actual is original for (actual, _), original in zip(result, chunks))
    assert chunks == [a, b, a]
    assert reranker.rerank("different", chunks) == result


def test_identity_singleton_has_normalized_score():
    a = chunk("a", "contract")
    assert IdentityReranker().rerank("", (a,)) == [(a, 1.0)]


def test_overlap_reorders_by_normalized_unique_query_coverage():
    a = chunk("a", "unrelated", title="contract payment")
    b = chunk("b", "contract contract")
    c = chunk("c", "payment contract extra")
    chunks = [a, b, c]
    reranker: Reranker = LexicalOverlapReranker()
    result = reranker.rerank("contract payment contract", chunks)
    assert result == [(c, 1.0), (b, 0.5), (a, 0.0)]
    assert result[0][0] is c and result[1][0] is b and result[2][0] is a
    assert chunks == [a, b, c]


def test_overlap_ties_keep_input_order_and_duplicates():
    a, b, c = (chunk("z", "contract"), chunk("a", "payment"),
               chunk("c", "contract payment"))
    assert LexicalOverlapReranker().rerank("contract payment", [a, b, c, a]) == [
        (c, 1.0), (a, 0.5), (b, 0.5), (a, 0.5),
    ]


@pytest.mark.parametrize("reranker", [IdentityReranker(), LexicalOverlapReranker()])
def test_empty_input(reranker):
    assert reranker.rerank("계약 대금", []) == []


@pytest.mark.parametrize("query", ["", "   ", "CIVIL OR AND NOT [NAME] a !"])
def test_no_usable_query_terms_scores_zero_and_keeps_order(query):
    a, b = chunk("z", "contract"), chunk("a", "payment")
    assert LexicalOverlapReranker().rerank(query, (a, b)) == [(a, 0.0), (b, 0.0)]


def test_korean_query_reuses_lexical_punctuation_and_mask_rules():
    a, b, c = (chunk("a", "별도 안내"), chunk("b", "계약, 계약"),
               chunk("c", "계약 대금."))
    assert LexicalOverlapReranker().rerank("CIVIL 계약, 대금? [NAME]", [a, b, c]) == [
        (c, 1.0), (b, 0.5), (a, 0.0),
    ]


def test_terms_match_whole_tokens_with_existing_case_rules():
    a, b = chunk("a", "contracts Contract"), chunk("b", "contract")
    assert LexicalOverlapReranker().rerank("contract", [a, b]) == [(b, 1.0), (a, 0.0)]
