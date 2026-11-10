from dataclasses import replace

import pytest

from rag_research_agent.rag.citations import format_citations
from rag_research_agent.rag.guidance import GuidanceEvidence


A = GuidanceEvidence("a:1", "A", "[NAME] 안내", "v1", "[PHONE]으로 확인")
B = GuidanceEvidence("b:1", "B", "두 번째 안내", "v2", "마스킹된 본문")
A2 = replace(A, chunk_id="a:2", safe_text="다른 청크")
HASHES = {"A": "abcdef01" + "0" * 56, "B": "12345678" + "f" * 56}


@pytest.mark.parametrize("format,heading,title", [
    ("markdown", "## 참고자료", r"\[NAME\] 안내"),
    ("text", "참고자료", "[NAME] 안내"),
])
def test_formats_number_in_citation_order_and_exclude_uncited_evidence(format, heading, title):
    result = format_citations("답변 그대로", [B.chunk_id, A.chunk_id], [A, A2, B],
                              document_hashes=HASHES, format=format)
    prefix = "- " if format == "markdown" else ""
    assert result == (
        f"답변 그대로\n\n[1] [2]\n\n{heading}\n"
        f"{prefix}[1] 두 번째 안내 · 출처 ID: B · 문서 hash: 12345678\n"
        f"{prefix}[2] {title} · 출처 ID: A · 문서 hash: abcdef01"
    )
    only_a = format_citations("답변", [A.chunk_id], [B, A], document_hashes=HASHES, format=format)
    assert "두 번째 안내" not in only_a and "12345678" not in only_a
    assert A.safe_text not in result and B.safe_text not in result


def test_repeated_chunks_and_different_chunks_of_same_document_share_one_number():
    result = format_citations("답변", [A2.chunk_id, A.chunk_id, A2.chunk_id, B.chunk_id],
                              [A, B, A2], document_hashes=HASHES, format="text")
    assert result.splitlines()[2] == "[1] [2]"
    assert result.count("출처 ID: A") == 1
    assert "[3]" not in result


@pytest.mark.parametrize("format", ["markdown", "text"])
def test_no_citations_preserves_answer_exactly(format):
    answer = "본문\n\n공백 유지  \n"
    assert format_citations(answer, [], [A], document_hashes={}, format=format) == answer


@pytest.mark.parametrize("unknown", ["missing:1", "A"])
def test_unknown_chunk_id_and_document_id_instead_of_chunk_id_are_rejected(unknown):
    with pytest.raises(ValueError, match="outside"):
        format_citations("답변", [A.chunk_id, unknown], [A], document_hashes=HASHES)


@pytest.mark.parametrize("hashes", [{}, {"A": "v1"}, {"A": "g" * 64}])
def test_missing_or_invalid_document_hash_is_rejected(hashes):
    with pytest.raises(ValueError, match="SHA-256"):
        format_citations("답변", [A.chunk_id], [A], document_hashes=hashes)


def test_markdown_metadata_is_literal_and_cannot_add_reference_lines():
    item = replace(A, title="[NAME](link) <tag>\n## heading", document_id="A*[1]")
    result = format_citations("답변", [A.chunk_id], [item],
                              document_hashes={item.document_id: HASHES["A"]})
    assert r"\[NAME\]\(link\) \<tag\> \#\# heading" in result
    assert r"출처 ID: A\*\[1\]" in result
    assert len(result.splitlines()) == 6


def test_unsupported_format_is_rejected_even_without_citations():
    with pytest.raises(ValueError, match="format"):
        format_citations("답변", [], [], document_hashes={}, format="html")


def test_conflicting_duplicate_chunk_ids_are_rejected():
    with pytest.raises(ValueError, match="conflicting"):
        format_citations("답변", [A.chunk_id], [A, replace(A, document_id="B")],
                         document_hashes=HASHES)
