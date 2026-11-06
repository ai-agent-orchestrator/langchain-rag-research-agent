"""LAB: turn a long stored prompt (40+ pages) into a task-focused brief under a budget.

    long prompt -> segments -> security pass (mask PII, flag injection, exclude flagged)
                -> score segments for the task: head | keyword | vector | hybrid
                   (hybrid = RRF of BM25 on the expanded query and vector similarity,
                    plus a must-keep boost for constraints, decisions and numbers)
                -> MMR selection under the character budget -> original order -> brief

The brief is extractive by default: every sentence is copied from the source, so nothing
can be invented. An optional abstractive step (summarize.py) is checked against the source.
"""
from __future__ import annotations

MATURITY = "lab"

import re
from dataclasses import dataclass, field
from typing import Callable, Sequence

from memvid_guardrail.guard.masking import mask_pii
from memvid_guardrail.lab.briefing.keywords import BM25, expand_query, tokenize
from memvid_guardrail.lab.hybrid import rrf

Encode = Callable[[Sequence[str]], list[list[float]]]
STRATEGIES = ("head", "keyword", "vector", "hybrid")

# Fixed injection rules (explainable). The lab semantic guard can be added on top.
INJECTION_RULES = (
    ("IGNORE_INSTRUCTIONS", r"(?:이전|앞|위|기존|모든)\s*(?:의\s*)?(?:지시|명령|규칙|지침).{0,12}(?:무시|잊)|ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions"),
    ("REVEAL_SYSTEM", r"시스템\s*프롬프트.{0,12}(?:공개|출력|보여)|reveal.{0,20}system\s+prompt"),
    ("ROLE_OVERRIDE", r"(?:지금부터|이제부터)\s*(?:너는|당신은).{0,20}(?:제한\s*없|무엇이든)|you\s+are\s+now\s+(?:dan|unrestricted)"),
    ("EXFILTRATE", r"(?:토큰|비밀\s*키|api\s*key|비밀번호).{0,20}(?:보내|전송|업로드|출력)"),
)
MUST_KEEP = re.compile(r"반드시|절대|금지|하지\s*않는다|하지\s*말|필수|마감|기한|결정\s*[A-Z]-?\d+|D-\d{2,}|\b(?:must|never|do not)\b", re.I)
STALE = re.compile(r"폐기|초기안|더 이상 쓰지 않|superseded|deprecated|obsolete", re.I)
NUMERIC = re.compile(r"\d[\d,.]*\s*(?:자|개|일|시간|분|%|원|만원|건|쪽|회)|\d{4}-\d{2}-\d{2}")


@dataclass(frozen=True)
class Segment:
    index: int
    text: str                 # masked text
    chars: int
    injection: tuple[str, ...] = ()
    must_keep: bool = False
    stale: bool = False       # superseded/obsolete marker: kept, but ranked last and never boosted


@dataclass
class Brief:
    strategy: str
    text: str
    selected: list[int]
    excluded_injection: list[int]
    expanded_terms: list[str] = field(default_factory=list)
    budget: int = 0
    stale_included: list[int] = field(default_factory=list)


def segment(text: str, max_chars: int = 700) -> list[str]:
    """Paragraphs (blank-line separated); long paragraphs are cut at sentence ends."""
    out: list[str] = []
    for para in re.split(r"\n\s*\n", text):
        para = para.strip()
        if not para:
            continue
        if len(para) <= max_chars:
            out.append(para)
            continue
        current = ""
        for sent in re.split(r"(?<=[.!?。다])\s+", para):
            if current and len(current) + len(sent) + 1 > max_chars:
                out.append(current)
                current = ""
            current = f"{current} {sent}".strip()
        if current:
            out.append(current)
    return out


def security_pass(parts: Sequence[str]) -> list[Segment]:
    segs = []
    for i, raw in enumerate(parts):
        text = mask_pii(raw)
        flags = tuple(code for code, rule in INJECTION_RULES if re.search(rule, text, re.I | re.S))
        stale = bool(STALE.search(text))
        keep = bool(MUST_KEEP.search(text) or NUMERIC.search(text)) and not stale
        segs.append(Segment(i, text, len(text), flags, keep, stale))
    return segs


def _cosine_scores(encode: Encode, task: str, texts: Sequence[str]) -> list[float]:
    vectors = encode(list(texts))
    q = encode([task])[0]
    return [sum(a * b for a, b in zip(q, v)) for v in vectors]


def _select(order: Sequence[int], segs: Sequence[Segment], budget: int, similarity: Callable[[int, int], float],
            diversity: float) -> list[int]:
    """MMR over a rank order: walk candidates best-first, skip near-copies of chosen ones."""
    chosen: list[int] = []
    used = 0
    rank_score = {idx: 1.0 - pos / max(len(order), 1) for pos, idx in enumerate(order)}
    pool = list(order)
    while pool:
        best = max(pool, key=lambda i: (1 - diversity) * rank_score[i]
                   - diversity * max((similarity(i, c) for c in chosen), default=0.0))
        pool.remove(best)
        if used + segs[best].chars + 1 <= budget:
            chosen.append(best)
            used += segs[best].chars + 1
    return sorted(chosen)


def build_brief(text: str, task: str, budget: int = 12000, strategy: str = "hybrid",
                encode: Encode | None = None, must_keep_boost: int = 15, diversity: float = 0.3,
                segment_chars: int = 700) -> Brief:
    if strategy not in STRATEGIES:
        raise ValueError(f"unknown strategy: {strategy}")
    segs = security_pass(segment(text, segment_chars))
    excluded = [s.index for s in segs if s.injection]
    usable = [s for s in segs if not s.injection]
    texts = [s.text for s in usable]
    expanded: list[str] = []
    if strategy == "head" or not usable:
        picked, used = [], 0
        for s in usable:
            if used + s.chars + 1 > budget:
                break
            picked.append(s.index)
            used += s.chars + 1
        return Brief(strategy, "\n\n".join(segs[i].text for i in picked), picked, excluded, [], budget)

    rankings: list[list[int]] = []
    bm25 = BM25(texts)
    if strategy in ("keyword", "hybrid"):
        expanded = expand_query(mask_pii(task), texts, bm25) if strategy == "hybrid" else tokenize(task)
        scores = bm25.scores(expanded)
        rankings.append([usable[i].index for i in sorted(range(len(usable)), key=lambda i: -scores[i]) if scores[i] > 0])
    if strategy in ("vector", "hybrid"):
        if encode is None:
            raise ValueError("vector strategies need an encoder")
        scores = _cosine_scores(encode, mask_pii(task), texts)
        rankings.append([usable[i].index for i in sorted(range(len(usable)), key=lambda i: -scores[i])])
    if strategy == "hybrid":
        fused = [int(i) for i, _ in rrf([[str(x) for x in r] for r in rankings])]
        keep = [i for i in fused if segs[i].must_keep]
        # Must-keep segments that are on-task move up by a fixed number of places.
        order = []
        for pos, i in enumerate(fused):
            order.append((pos - (must_keep_boost if i in keep else 0), pos, i))
        order = [i for _, _, i in sorted(order)]
    else:
        order = rankings[0]
    # Superseded material is never deleted, but every current segment outranks it.
    order = [i for i in order if not segs[i].stale] + [i for i in order if segs[i].stale]
    token_sets = {s.index: set(tokenize(s.text)) for s in usable}

    def jaccard(a: int, b: int) -> float:
        x, y = token_sets[a], token_sets[b]
        return len(x & y) / (len(x | y) or 1)
    picked = _select(order, segs, budget, jaccard, diversity)
    return Brief(strategy, "\n\n".join(segs[i].text for i in picked), picked, excluded, expanded, budget,
                 [i for i in picked if segs[i].stale])
