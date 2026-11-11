"""Opt-in legal skeleton: lexical statute/status and date-order checks, not legal advice.

Import this module explicitly before get_filter("legal"). Cold lazy loading needs
the central BUILTINS declaration to be extended in a follow-up outside R18's scope.
"""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass
from datetime import date
import re

from rag_research_agent.guard.domain_filter import BUILTINS, InputDecision, Issue, Verdict, register

VERSION = "legal-filter/1"
DISCLAIMER = "법률 자문이 아닙니다"
_BRANCHES = (
    ("criminal", ("형사", "고소", "고발", "사기", "폭행", "절도")),
    ("family", ("가사", "이혼", "양육", "상속", "친권")),
    ("civil", ("민사", "계약", "손해배상", "임대차", "대여금")),
)
_STATUTE = re.compile(r"제\d+조")
_REPEALED = re.compile(r"폐지|삭제|구법")
_CLAUSE = re.compile(r"(?<=[.!?。])\s+|[\n;,]+")
_DATE = re.compile(
    r"(?<!\d)(?P<year>\d{4})(?:-(?P<month>\d{1,2})-(?P<day>\d{1,2})(?!\d)"
    r"|년\s*(?P<ko_month>\d{1,2})월\s*(?P<ko_day>\d{1,2})일)"
)


def _dates(text: str) -> list[date]:
    """Unique valid full dates in mention order; ISO and Korean forms share keys."""
    dates = []
    for match in _DATE.finditer(text):
        try:
            value = date(int(match["year"]), int(match["month"] or match["ko_month"]),
                         int(match["day"] or match["ko_day"]))
        except ValueError:
            continue
        if value not in dates:
            dates.append(value)
    return dates


@dataclass(frozen=True)
class LegalFilter:
    name: str = "legal"
    version: str = VERSION

    def check_input(self, text: str) -> InputDecision:
        if not (text or "").strip():
            return InputDecision(False, "EMPTY_INPUT")
        # Mixed keywords use a fixed precedence: criminal, family, civil, other.
        for branch, cues in _BRANCHES:
            if any(cue in text for cue in cues):
                return InputDecision(True, branch=branch)
        return InputDecision(True, branch="other")

    def verify(self, answer: str, evidence: tuple[str, ...], branch: str = "default") -> Verdict:
        if not any(text.strip() for text in evidence):
            return Verdict(False, (Issue("NO_EVIDENCE", False),))
        if not answer.strip():
            return Verdict(False, (Issue("EMPTY_ANSWER", True),))
        source = "\n".join(evidence)
        cited = set(_STATUTE.findall(answer))
        unsupported = cited - set(_STATUTE.findall(source))
        # Status applies only within a punctuation-delimited clause of one source.
        repealed = {statute for text in evidence for clause in _CLAUSE.split(text)
                    if _REPEALED.search(clause) for statute in _STATUTE.findall(clause)}
        issues = []
        if unsupported:
            issues.append(Issue("UNSUPPORTED_STATUTE", True, len(unsupported)))
        if cited & repealed:
            issues.append(Issue("REPEALED_CITED", True, len(cited & repealed)))
        source_dates, answer_dates = _dates(source), _dates(answer)
        shared = set(source_dates) & set(answer_dates)
        if ([d for d in source_dates if d in shared] != [d for d in answer_dates if d in shared]):
            issues.append(Issue("TIMELINE_MIXED", True))
        return Verdict(not issues, tuple(issues))

    def finalize(self, answer: str, branch: str = "default") -> str:
        return answer.rstrip() + "\n\n" + DISCLAIMER


register("legal", LegalFilter)
BUILTINS["legal"] = __name__
