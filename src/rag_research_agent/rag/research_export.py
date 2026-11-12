"""Opt-in, offline exports of already-masked research results; no file I/O."""
from __future__ import annotations

MATURITY = "incubating"

from html import escape
import re
from typing import TYPE_CHECKING

from rag_research_agent.core.research import span_matches

if TYPE_CHECKING:
    from rag_research_agent.rag.research_graph import ResearchResult


def _citations(result: ResearchResult):
    sources = {source.source_id: source for source in result.sources}
    claims = {claim.claim_id: claim for claim in result.claims}
    numbers, notes, sentences = {}, [], []
    for sentence in result.draft.sentences:
        refs = []
        for claim_id in dict.fromkeys(sentence.claim_ids):
            claim = claims.get(claim_id)
            if claim is None or not span_matches(claim, sources):
                raise ValueError("cannot export an unresolved or invalid citation")
            key = (claim.source_id, claim.start, claim.end)
            if key not in numbers:
                numbers[key] = len(notes) + 1
                notes.append((claim.source_id, claim.start, claim.end,
                              sources[claim.source_id].text[claim.start:claim.end]))
            refs.append(numbers[key])
        sentences.append((sentence.text, tuple(dict.fromkeys(refs))))
    return sentences, notes


def _review(result: ResearchResult) -> list[str]:
    if result.verify_codes:
        lines = ["검수 미통과 항목: " + code for code in result.verify_codes]
    elif "verify" in result.path and not result.stopped and not result.interrupts:
        lines = ["검수 통과 (미통과 항목 없음)"]
    else:
        lines = ["검수 미검증"]
    if result.stopped:
        lines.append("연구 중단: " + result.stopped)
    if result.interrupts:
        lines.append("검토 대기 중")
    return lines


def _md(text: str) -> str:
    # Treat all caller text as literal content, including raw HTML and Markdown.
    return re.sub(r"([\\`*_{}\[\]()#+.!|>~-])", r"\\\1", escape(text)).replace("\n", " ").replace("\r", " ")


def export_markdown(result: ResearchResult) -> str:
    """Return Markdown footnotes numbered by first use, with zero-based [start:end] spans.

    Unresolvable citations raise ValueError rather than fabricating evidence. Inputs
    must already be masked; this renderer does not perform privacy filtering.
    """
    sentences, notes = _citations(result)
    lines = ["# 리서치 보고서", ""]
    for text, refs in sentences:
        lines += [_md(text) + "".join(f"[^{n}]" for n in refs), ""]
    lines += ["## 출처 각주", ""]
    for n, (sid, start, end, quote) in enumerate(notes, 1):
        lines.append(f"[^{n}]: 문서 {_md(sid)} [{start}:{end}] — {_md(quote)}")
    lines += ["", "## 검수 상태", ""] + ["- " + _md(line) for line in _review(result)]
    lines += ["", "## 부록", "", "노드 경로: " + _md(" → ".join(result.path)),
              "", f"추정 토큰: {result.shadow_tokens} (실제 사용량·과금 아님)", ""]
    lines += [f"- {_md(node)} / {_md(kind)}: {tokens}" for node, kind, tokens in result.cost]
    return "\n".join(lines) + "\n"


def export_html(result: ResearchResult) -> str:
    """Return a standalone HTML document; all input text is escaped, never markup."""
    sentences, notes = _citations(result)
    parts = ['<!doctype html><html lang="ko"><head><meta charset="utf-8">',
             '<title>리서치 보고서</title></head><body><h1>리서치 보고서</h1>']
    for text, refs in sentences:
        links = "".join(f'<sup><a href="#fn-{n}">[{n}]</a></sup>' for n in refs)
        parts.append("<p>" + escape(text) + links + "</p>")
    parts.append('<section><h2>출처 각주</h2><ol>')
    for n, (sid, start, end, quote) in enumerate(notes, 1):
        parts.append(f'<li id="fn-{n}">문서 {escape(sid)} [{start}:{end}] — '
                     f'<q>{escape(quote)}</q></li>')
    parts.append('</ol></section><section><h2>검수 상태</h2><ul>')
    parts += ["<li>" + escape(line) + "</li>" for line in _review(result)]
    parts += ['</ul></section><section><h2>부록</h2>',
              '<p>노드 경로: ' + escape(" → ".join(result.path)) + '</p>',
              f'<p>추정 토큰: {result.shadow_tokens} (실제 사용량·과금 아님)</p><ul>']
    parts += [f'<li>{escape(node)} / {escape(kind)}: {tokens}</li>'
              for node, kind, tokens in result.cost]
    parts.append('</ul></section></body></html>')
    return "\n".join(parts) + "\n"
