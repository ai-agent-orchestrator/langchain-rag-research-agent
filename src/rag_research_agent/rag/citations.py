"""Display citations using supplied, already masked evidence; never reopen sources."""
from __future__ import annotations

MATURITY = "incubating"

from collections.abc import Mapping, Sequence
import re

from rag_research_agent.rag.answer import EvidenceLike


def _markdown(text: str) -> str:
    # Metadata is literal text, including titles that happen to contain Markdown/HTML.
    return re.sub(r"([\\`*_{}\[\]()<>#+.!|~-])", r"\\\1", text)


def format_citations(
    answer: str,
    citation_ids: Sequence[str],
    evidence: Sequence[EvidenceLike],
    *,
    document_hashes: Mapping[str, str],
    format: str = "markdown",
) -> str:
    """Append answer-level [n] markers and references in first-citation order.

    IDs are chunk IDs, as in GuidanceReply/GuidanceDraft. Evidence uses the existing
    GuidanceEvidence shape. Repeated document IDs share a number (first title wins).
    The caller supplies trusted document SHA-256 values separately: that DTO has no
    document hash. Chunk hashes and source_version are not document hashes.

    Answer and metadata must already be masked and checked by the caller. This
    function neither masks nor verifies provenance or the truth of a supplied hash.
    No sentence-level attribution is inferred from an answer-level citation list.
    """
    if format not in {"markdown", "text"}:
        raise ValueError("format must be 'markdown' or 'text'")
    by_id = {}
    for item in evidence:
        if item.chunk_id in by_id and by_id[item.chunk_id] != item:
            raise ValueError("conflicting evidence for chunk ID")
        by_id[item.chunk_id] = item
    sources = {}
    for citation_id in citation_ids:
        if citation_id not in by_id:
            raise ValueError("citation outside the retrieved evidence")
        item = by_id[citation_id]
        sources.setdefault(item.document_id, item)
    if not sources:
        return answer

    render = _markdown if format == "markdown" else lambda value: value
    references = []
    for number, (document_id, item) in enumerate(sources.items(), 1):
        digest = document_hashes.get(document_id, "")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            raise ValueError("cited document requires a SHA-256 hash")
        title = " ".join(item.title.splitlines())
        source_id = " ".join(document_id.splitlines())
        prefix = "- " if format == "markdown" else ""
        references.append(
            f"{prefix}[{number}] {render(title)} · 출처 ID: {render(source_id)} · "
            f"문서 hash: {digest[:8].lower()}"
        )
    markers = " ".join(f"[{n}]" for n in range(1, len(sources) + 1))
    heading = "## 참고자료" if format == "markdown" else "참고자료"
    return f"{answer}\n\n{markers}\n\n{heading}\n" + "\n".join(references)
