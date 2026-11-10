"""Offline path tests using the real retry graph and deterministic rewriter."""
from types import SimpleNamespace

import pytest

from rag_research_agent.core.contracts import RetrievalUnavailable
from rag_research_agent.core.types import Status
from rag_research_agent.rag.query_rewrite import rewrite_queries
from rag_research_agent.rag.retry_graph import build_graph


QUERY = "2026년 비용 그리고 자료"
GROUPS = [
    [{"query": QUERY, "reason": "original"}],
    [
        {"query": "2026년 비용", "reason": "subquestion"},
        {"query": "자료", "reason": "subquestion"},
    ],
    [{"query": "비용 그리고 자료", "reason": "without_numeric_period"}],
]
SEARCH_QUERIES = [QUERY, "2026년 비용", "자료", "비용 그리고 자료"]


def chunk(source):
    return SimpleNamespace(
        chunk_id=f"{source}:c01", document_id=source, safe_text="핵심은 비용이다."
    )


class Library:
    """Same in-memory search seam as test_retry_graph; graph stages stay real."""

    def __init__(self, chunks, responses):
        self.chunks = chunks
        self.responses = responses
        self.calls = []

    def search(self, query, k, mode):
        self.calls.append((query, k, mode))
        response = self.responses[query]
        if isinstance(response, Exception):
            raise response
        return response


def test_identical_variants_end_after_original_search():
    query = "비용 자료"
    assert rewrite_queries(query) == []
    library = Library([], {query: []})

    result = build_graph(library, tau=0.5).invoke({"query": query})

    assert library.calls == [(query, 3, "vector")]
    assert len(result["attempts"]) == 1
    assert result["attempts"][0]["queries"] == [{"query": query, "reason": "original"}]
    assert result["attempts"][0]["hits"] == []
    assert result["attempts"][0]["top_score"] is None
    assert result["attempts"][0]["tau"] == 0.5
    assert result["attempts"][0]["sufficient"] is False
    assert result["status"] == Status.REQUEST_MORE
    assert result["final_prompt_input"] == ""
    assert result["generation_calls"] == 0


@pytest.mark.parametrize(
    ("query", "variants"),
    [
        ("2026년 3개월 10일", []),
        ("2026 3", [{"query": "2026", "reason": "keywords"}]),
        ("그리고 또 그리고", [{"query": "그리고", "reason": "subquestion"}]),
        (("자료 " * 10000).strip(), [{"query": "자료", "reason": "keywords"}]),
    ],
    ids=["numeric-period-only", "numeric-only", "connectives-only", "long-query"],
)
def test_edge_queries_have_bounded_deduplicated_attempts(query, variants):
    assert rewrite_queries(query) == variants
    item = chunk("one")
    queries = [query, *[variant["query"] for variant in variants]]
    library = Library([item], {text: [(item, 0.1, 1)] for text in queries})

    result = build_graph(library, tau=0.5).invoke({"query": query})

    expected_groups = [[{"query": query, "reason": "original"}]]
    if variants:
        expected_groups.append(variants)
    assert library.calls == [(text, 3, "vector") for text in queries]
    assert [attempt["queries"] for attempt in result["attempts"]] == expected_groups
    assert [attempt["attempt"] for attempt in result["attempts"]] == list(
        range(1, len(expected_groups) + 1)
    )
    assert all(attempt["top_score"] == 0.1 for attempt in result["attempts"])
    assert all(attempt["tau"] == 0.5 for attempt in result["attempts"])
    assert all(attempt["sufficient"] is False for attempt in result["attempts"])
    assert result["status"] == Status.REQUEST_MORE
    assert result["final_prompt_input"] == ""
    assert result["generation_calls"] == 0


@pytest.mark.parametrize("third_score", [0.5, 0.49], ids=["at-tau", "below-tau"])
def test_third_attempt_boundary_and_complete_ordered_history(third_score):
    a, b, c = chunk("a"), chunk("b"), chunk("c")
    library = Library([a, b, c], {
        QUERY: [(a, 0.1, 1)],
        "2026년 비용": [(b, 0.2, 1)],
        "자료": [(c, 0.3, 1)],
        "비용 그리고 자료": [(a, third_score, 1)],
    })

    result = build_graph(library, tau=0.5).invoke({"query": QUERY})

    assert library.calls == [(text, 3, "vector") for text in SEARCH_QUERIES]
    attempts = result["attempts"]
    assert len(attempts) == 3
    assert [attempt["attempt"] for attempt in attempts] == [1, 2, 3]
    assert [attempt["queries"] for attempt in attempts] == GROUPS
    assert [attempt["hits"] for attempt in attempts] == [
        [{"chunk_id": "a:c01", "score": 0.1, "rank": 1}],
        [
            {"chunk_id": "c:c01", "score": 0.3, "rank": 1},
            {"chunk_id": "b:c01", "score": 0.2, "rank": 2},
            {"chunk_id": "a:c01", "score": 0.1, "rank": 3},
        ],
        [
            {"chunk_id": "a:c01", "score": third_score, "rank": 1},
            {"chunk_id": "c:c01", "score": 0.3, "rank": 2},
            {"chunk_id": "b:c01", "score": 0.2, "rank": 3},
        ],
    ]
    assert [attempt["top_score"] for attempt in attempts] == [0.1, 0.3, third_score]
    assert [attempt["tau"] for attempt in attempts] == [0.5, 0.5, 0.5]
    sufficient = third_score >= 0.5
    assert [attempt["sufficient"] for attempt in attempts] == [False, False, sufficient]
    assert result["status"] == (Status.OK if sufficient else Status.REQUEST_MORE)
    assert result["generation_calls"] == 0
    if sufficient:
        assert result["final_prompt_input"]
        assert "compose_and_check" in result["node_calls"]
    else:
        assert result["final_prompt_input"] == ""


@pytest.mark.parametrize("max_retries", [0, 1, 2])
def test_retry_limit_counts_attempt_groups_not_search_calls(max_retries):
    library = Library([], {text: [] for text in SEARCH_QUERIES})

    result = build_graph(library, tau=0.5, max_retries=max_retries).invoke({"query": QUERY})

    assert len(result["attempts"]) == max_retries + 1
    assert [attempt["queries"] for attempt in result["attempts"]] == GROUPS[:max_retries + 1]
    call_count = [1, 3, 4][max_retries]
    assert library.calls == [(text, 3, "vector") for text in SEARCH_QUERIES[:call_count]]
    assert result["status"] == Status.REQUEST_MORE
    assert result["final_prompt_input"] == ""
    assert result["generation_calls"] == 0


@pytest.mark.parametrize("failed_query", SEARCH_QUERIES[1:])
def test_retrieval_failure_propagates_from_retry_without_request_more(failed_query):
    item = chunk("one")
    failure = RetrievalUnavailable("offline retrieval failure")
    responses = {text: [(item, 0.1, 1)] for text in SEARCH_QUERIES}
    responses[failed_query] = failure
    library = Library([item], responses)

    with pytest.raises(RetrievalUnavailable) as caught:
        build_graph(library, tau=0.5).invoke({"query": QUERY})

    assert caught.value is failure
    expected = SEARCH_QUERIES[:SEARCH_QUERIES.index(failed_query) + 1]
    assert library.calls == [(text, 3, "vector") for text in expected]
