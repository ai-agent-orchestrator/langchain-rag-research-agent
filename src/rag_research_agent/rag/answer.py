"""B03 response contract: the model fills a small structured draft; the server validates
citations, checks every field, and assembles the external `answer` string itself.

Evidence objects are duck-typed (chunk_id, document_id, title, source_version, safe_text) so
this module does not depend on a particular retrieval implementation.
"""
from __future__ import annotations

MATURITY = "incubating"

from enum import StrEnum
from typing import Callable, Protocol, Sequence

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

NOT_INVOKED_MODEL = "not-invoked"
MAX_ANSWER_CHARS = 1500
NO_EVIDENCE_ANSWER = (
    "등록된 안내 자료에서 관련 근거를 찾지 못했습니다. "
    "사건 경위를 날짜순으로 정리하고, 계약서·대화 기록·입금 내역 등 현재 보유한 자료를 "
    "준비해 상담에서 전문가와 확인해 주세요."
)


class EvidenceStatus(StrEnum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"


class EvidenceLike(Protocol):
    chunk_id: str
    document_id: str
    title: str
    source_version: str
    safe_text: str


class DraftRejected(Exception):
    """The model output is malformed or cites something we did not retrieve. Never published."""
    code = "AI_DRAFT_REJECTED"


class GuidanceDraft(BaseModel):
    """What the model may produce. evidenceStatus is never accepted from the model."""
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid",
                              str_strip_whitespace=True)
    answer: str = Field(min_length=1, max_length=600)
    preparation_items: list[str] = Field(default_factory=list, max_length=8)
    questions: list[str] = Field(default_factory=list, max_length=5)
    citation_ids: list[str] = Field(min_length=1, max_length=5)


def validate_citations(draft: GuidanceDraft, evidence: Sequence[EvidenceLike]) -> list[EvidenceLike]:
    by_id = {e.chunk_id: e for e in evidence}
    unknown = [c for c in draft.citation_ids if c not in by_id]
    if unknown or not draft.citation_ids:
        raise DraftRejected("citation outside the retrieved evidence")
    seen, cited = set(), []
    for cid in draft.citation_ids:
        if cid not in seen:
            seen.add(cid)
            cited.append(by_id[cid])
    return cited


def assemble_answer(draft: GuidanceDraft, evidence: Sequence[EvidenceLike],
                    check: Callable[[str], str]) -> str:
    """`check` is the server's field-level output check + final masking. It returns safe text
    or raises; it is applied to every field and again to the assembled string."""
    cited = validate_citations(draft, evidence)
    for item in draft.preparation_items + draft.questions:
        if not item or len(item) > 120:
            raise DraftRejected("list item empty or too long")
    lines = [f"[안내] {check(draft.answer)}"]
    if draft.preparation_items:
        lines.append("[준비자료]")
        lines.extend(f"- {check(item)}" for item in draft.preparation_items)
    if draft.questions:
        lines.append("[확인할 질문]")
        lines.extend(f"- {check(item)}" for item in draft.questions)
    # Sources are rendered from our records, never from model text.
    sources = ", ".join(f"{e.document_id} · {e.title} · {e.source_version}" for e in
                        {e.document_id: e for e in cited}.values())
    lines.append(f"[참고자료] {sources}")
    text = check("\n".join(lines))
    if len(text) > MAX_ANSWER_CHARS:
        raise DraftRejected("assembled answer too long")
    return text


def no_evidence_answer(check: Callable[[str], str]) -> str:
    return check(NO_EVIDENCE_ANSWER)
