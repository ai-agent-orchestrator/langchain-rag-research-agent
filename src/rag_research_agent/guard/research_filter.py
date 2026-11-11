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

from rag_research_agent.guard.domain_filter import InputDecision, Issue, Verdict, register

VERSION = "research-filter/1"

CAUSAL_CUES = ("때문에", "때문", "따라서", "그 결과", "결과적으로", "으로 인해", "로 인해", "원인", "이유로",
               "그래서", "덕분에", "탓에", "초래", "야기", "이어진", "이어져", "이끌", "because", "therefore",
               "as a result", "leads to", "led to", "caused", "due to", "results in")
CONSTRAINT_CUES = ("단,", "다만", "제약", "한계", "조건", "이상일 때", "이하일 때", "경우에만", "하지 않는다",
                   "금지", "제외", "only if", "unless", "except", "must not", "limited to")
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
    return any(c in low for c in cues)


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


register("research", ResearchFilter)
