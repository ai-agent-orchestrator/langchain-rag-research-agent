"""Research-domain filter: keeps causality, constraints and concrete facts when sources are summarised.

Risks it targets (docs/DOMAIN_FILTERS.ko.md, row 3):
- facts not in the source (numbers, years, percentages)     -> UNSUPPORTED_NUMBER (retryable)
- sentences with no footing in the evidence                 -> UNGROUNDED_SENTENCE (retryable)
- cause-and-effect present in the evidence, absent in answer -> CAUSAL_LOSS (retryable)
- a stated limit/condition dropped                           -> CONSTRAINT_DROPPED (retryable)
- shallow, generic summary (low density of concrete content) -> LOW_DENSITY (retryable)
- an answer but no evidence to check it against              -> NO_EVIDENCE (not retryable)

Rule-based and deterministic. Cue lists are versioned data in this file; change them -> bump VERSION.
"""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass
import re

from rag_research_agent.core.research import Draft, ResearchPlan
from rag_research_agent.guard.domain_filter import InputDecision, Issue, Verdict, register

VERSION = "research-filter/1"

CAUSAL_CUES = ("때문에", "때문", "따라서", "그 결과", "결과적으로", "으로 인해", "로 인해", "원인", "이유로",
               "그래서", "덕분에", "탓에", "초래", "야기", "이어진", "이어져", "이끌", "because", "therefore",
               "as a result", "leads to", "led to", "caused", "due to", "results in")
CONSTRAINT_CUES = ("단,", "다만", "제약", "조건", "이상일 때", "이하일 때", "경우에만", "에만 ", "에 한정", "한정된",
                   "하지 않는다", "금지", "제외", "대상으로 하며", "only if", "unless", "except", "must not", "limited to")
# "X(으)로 ... 증가/감소했다": cause marked by the instrumental particle, effect by a change verb
CAUSAL_PATTERN = re.compile(r"(?:하락|상승|인상|인하|확대|축소|도입|증가|감소|개선|악화|변화|부족|완화|강화|규제|자동화|보급)(?:으로|로)\s[^.!?]*?(?:증가|감소|개선|하락|상승|절감|늘었|줄었|늘어|줄어|악화|회복|이어)")
CLICHE_CUES = ("일반적으로", "다양한", "여러 가지", "중요하다", "중요합니다", "필요하다", "필요합니다",
               "많은 사람", "다방면", "종합적으로", "결론적으로 말하면", "it is important", "various",
               "in general", "many factors")
_JOSA = re.compile(r"(으로|에서|에게|까지|부터|이다|이며|하고|하는|하여|했다|한다|들은|들이|들을|에는|으로는|와|과|은|는|이|가|을|를|의|에|로|도|만)$")
_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?")
_CITATION = re.compile(r"\[[^\]]{1,20}\]")
_SENTENCE = re.compile(r"(?<=[.!?。])\s+|\n+")
_TERM = re.compile(r"[가-힣A-Za-z][가-힣A-Za-z0-9_\-]+")


def _sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE.split(text or "") if s and len(s.strip()) > 1]


def _terms(text: str) -> set[str]:
    out = set()
    for raw in _TERM.findall(text or ""):
        term = _JOSA.sub("", raw.lower())
        if len(term) >= 2:
            out.add(term)
    return out


def _numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in _NUMBER.findall(_CITATION.sub(" ", text or ""))}


def _has(text: str, cues) -> bool:
    low = (text or "").lower()
    if any(c in low for c in cues):
        return True
    return cues is CAUSAL_CUES and bool(CAUSAL_PATTERN.search(text or ""))


@dataclass(frozen=True)
class ResearchFilter:
    name: str = "research"
    version: str = VERSION
    min_grounding: float = 0.5      # share of a sentence's terms that must appear in the evidence
    min_terms: int = 2              # sentences with fewer content terms are not judged for grounding
    min_density: float = 0.5        # share of answer sentences that carry concrete content
    max_input_chars: int = 20000

    def check_input(self, text: str) -> InputDecision:
        stripped = (text or "").strip()
        if not stripped:
            return InputDecision(False, "EMPTY_INPUT")
        if len(stripped) > self.max_input_chars:
            return InputDecision(False, "INPUT_TOO_LONG")
        return InputDecision(True, branch="research")

    def verify(self, answer: str, evidence: tuple[str, ...], branch: str = "default") -> Verdict:
        if not evidence:
            return Verdict(False, (Issue("NO_EVIDENCE", retryable=False),))
        source = "\n".join(evidence)
        source_terms, source_numbers = _terms(source), _numbers(source)
        sentences = _sentences(_CITATION.sub(" ", answer))
        if not sentences:
            return Verdict(False, (Issue("EMPTY_ANSWER", retryable=True),))
        issues: list[Issue] = []

        unsupported = sorted(_numbers(answer) - source_numbers)
        if unsupported:
            issues.append(Issue("UNSUPPORTED_NUMBER", True, len(unsupported)))

        ungrounded, concrete = 0, 0
        for sentence in sentences:
            terms = _terms(sentence)
            hits = sum(1 for t in terms if t in source_terms or any(t in s for s in source_terms if len(t) >= 3))
            if len(terms) >= self.min_terms and hits / len(terms) < self.min_grounding:
                ungrounded += 1
            specific = hits >= 3 and not _has(sentence, CLICHE_CUES)
            if _numbers(sentence) or _has(sentence, CAUSAL_CUES) or _has(sentence, CONSTRAINT_CUES) or specific:
                concrete += 1
        if ungrounded:
            issues.append(Issue("UNGROUNDED_SENTENCE", True, ungrounded))

        if _has(source, CAUSAL_CUES) and not _has(answer, CAUSAL_CUES):
            issues.append(Issue("CAUSAL_LOSS", True))
        if _has(source, CONSTRAINT_CUES) and not _has(answer, CONSTRAINT_CUES):
            issues.append(Issue("CONSTRAINT_DROPPED", True))

        density = concrete / len(sentences)
        if density < self.min_density:
            issues.append(Issue("LOW_DENSITY", True))
        grounding = 1 - ungrounded / len(sentences)
        return Verdict(not issues, tuple(issues), (("density", round(density, 4)), ("grounding", round(grounding, 4))))

    def finalize(self, answer: str, branch: str = "default") -> str:
        return answer



def relevant_claims(plan: ResearchPlan, claims, anchors) -> list:
    """Causal/constraint claims that belong to the report: they mention a required metric, or they come
    from a source the report already relies on (the same document's cause or exception)."""
    sources = {c.source_id for c in anchors}
    return [c for c in claims if c.kind in ("causal", "constraint")
            and (c.source_id in sources or any(m in c.text for m in plan.required_metrics))]


CLAIM_ALIGNMENT_VERSION = "claim-alignment/1"
_CLAIM_PART = re.compile(r";|\n|(?<=[.!?。])\s+")
_CAUSE_LINK = re.compile(
    r"때문에|으로 인해|로 인해|따라서|그 결과|이어졌다|\b(?:leads to|led to|causes|caused|because|due to|therefore)\b",
    re.IGNORECASE,
)


def _causal_sides(text: str):
    link = _CAUSE_LINK.search(text)
    if link is None:
        return None
    left, right = _terms(text[:link.start()]), _terms(text[link.end():])
    if link.group().lower() in ("because", "due to"):
        left, right = right, left
    return (left, right) if left and right else None


def _claim_alignment(findings, by_id) -> tuple[str, ...]:
    """Conservative lexical check, not semantic entailment (alignment rules v1).

    Resolve citations per sentence. Numeric clauses must fit their closest lexical
    claim, so an unrelated cited claim cannot lend its numbers to another claim.
    Exact extracts are accepted before heuristics, including multi-clause extracts.
    """
    misquoted, overreach = False, False
    for sentence in findings:
        cited = [by_id[i] for i in sentence.claim_ids if i in by_id]
        if not cited:
            continue  # UNCITED is handled by the existing report checks.
        if any(sentence.text.strip() == c.text.strip() for c in cited):
            continue
        source_terms = set().union(*(_terms(c.text) for c in cited))
        terms = _terms(sentence.text)
        if terms and len(terms - source_terms) / len(terms) > 0.5:
            overreach = True
        for part in _CLAIM_PART.split(sentence.text):
            if not part.strip():
                continue
            part_terms = _terms(part)
            # Jaccard similarity ignores numbers, choosing the claim by its words.
            scores = [len(part_terms & _terms(c.text)) / max(1, len(part_terms | _terms(c.text)))
                      for c in cited]
            best = [c for c, score in zip(cited, scores) if score == max(scores)]
            numbers = _numbers(part)
            if numbers and not any(numbers <= _numbers(c.text) for c in best):
                misquoted = True
            sides = _causal_sides(part)
            if sides:
                for c in best:
                    original = _causal_sides(c.text)
                    if original:
                        direct = len(sides[0] & original[0]) + len(sides[1] & original[1])
                        reverse = len(sides[0] & original[1]) + len(sides[1] & original[0])
                        if reverse > direct:
                            overreach = True
    return tuple(code for code, failed in (("MISQUOTED", misquoted), ("OVERREACH", overreach)) if failed)


def verify_report(draft: Draft, plan: ResearchPlan, claims, metrics, *, expect_balance: bool = True,
                  check_claim_alignment: bool = False) -> tuple[str, ...]:
    """Claim-level check of a report built from graph State (docs/RESEARCH_GRAPH_DESIGN.ko.md 4).
    Each code tells the graph where to go back: GAP:<metric> -> targeted search, others -> rewrite.
    Opt-in alignment adds retryable MISQUOTED and OVERREACH; defaults are unchanged.
    """
    findings = [s for s in draft.sentences if not s.note]
    if not findings:
        return ("EMPTY_REPORT",)
    by_id = {c.claim_id: c for c in claims}
    codes: list[str] = []
    body = " ".join(s.text for s in findings)
    for metric in plan.required_metrics:
        if not any(metric in s.text and _NUMBER.search(s.text) for s in findings):
            codes.append("GAP:" + metric)
    known_numbers = {m.value for m in metrics} | {n for c in claims for n in _numbers(c.text)}
    if _numbers(body) - known_numbers:
        codes.append("UNSUPPORTED_NUMBER")
    if any(not s.claim_ids or any(i not in by_id for i in s.claim_ids) for s in findings):
        codes.append("UNCITED")
    if check_claim_alignment:
        codes.extend(_claim_alignment(findings, by_id))
    cited = [by_id[i] for s in findings for i in s.claim_ids if i in by_id]
    cited_ids = {c.claim_id for c in cited}
    relevant = relevant_claims(plan, claims, cited)
    if any(c.kind == "causal" and c.claim_id not in cited_ids for c in relevant):
        codes.append("CAUSAL_LOSS")
    if any(c.kind == "constraint" and c.claim_id not in cited_ids for c in relevant):
        codes.append("CONSTRAINT_DROPPED")
    if expect_balance and any(c.stance == "con" for c in claims) and not any(c.stance == "con" for c in cited):
        codes.append("ONE_SIDED")
    cliche = sum(1 for s in findings if _has(s.text, CLICHE_CUES) and not _numbers(s.text))
    if cliche * 2 > len(findings):
        codes.append("LOW_DENSITY")
    return tuple(codes)


register("research", ResearchFilter)
