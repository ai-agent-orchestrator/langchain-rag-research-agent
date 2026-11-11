"""Opt-in synthetic educational rules, not a diagnostic tool.

Import explicitly before get_filter("medical"). The graph's emergency reply and
cold lazy loading need follow-up wiring outside this module's scope.
"""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass
from decimal import Decimal
import re

from rag_research_agent.guard.domain_filter import BUILTINS, InputDecision, Issue, Verdict, register

VERSION = "medical-filter/2"
EMERGENCY_ANSWER = "응급 신호가 있습니다. 즉시 119에 연락하거나 응급실로 가세요."
DISCLAIMER = "합성·교육용 정보이며 의료 자문이 아닙니다. 전문의와 상담하세요."
_EMERGENCY = re.compile(r"흉통|호흡\s*곤란|의식\s*(?:저하|소실)|가슴\s*통증|심정지|심한\s*출혈")
_DIAGNOSIS = re.compile(r"확진|[가-힣A-Za-z]+병(?:이|은)?\s*확실|진단(?:이|은)?\s*확실")
_CLAUSE = re.compile(r"(?<=[.!?。])\s+|[\n;]+")
_DRUG = r"[가-힣A-Za-z][가-힣A-Za-z0-9_-]*"
_CONTRA_BEFORE = re.compile(rf"({_DRUG})\s*(?:복용(?:은|이)?\s*)?금기")
_CONTRA_AFTER = re.compile(rf"금기\s*(?:약물\s*)?[:：]\s*({_DRUG})")
_DOSE = re.compile(r"(?<![\w.])(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>mcg|mg|μg|µg|g|ml|정|캡슐)(?![A-Za-z])", re.I)


def _contraindications(text: str) -> set[str]:
    """Explicit 'drug is contraindicated' or 'contraindication: drug' forms only."""
    drugs = set()
    for clause in _CLAUSE.split(text):
        if re.search(r"금기(?:가|는)?\s*(?:아니|아님|아닙)", clause):
            continue
        for pattern in (_CONTRA_BEFORE, _CONTRA_AFTER):
            for match in pattern.finditer(clause):
                drug = match[1]
                if drug.endswith(("은", "는", "이", "가", "을", "를")):
                    drug = drug[:-1]
                if drug:
                    drugs.add(drug)
    return drugs


def _doses(text: str) -> set[tuple[Decimal, str]]:
    return {(Decimal(m["value"]), m["unit"].lower().replace("µ", "μ").replace("mcg", "μg"))
            for m in _DOSE.finditer(text)}


@dataclass(frozen=True)
class MedicalFilter:
    name: str = "medical"
    version: str = VERSION

    def check_input(self, text: str) -> InputDecision:
        if _EMERGENCY.search(text):
            return InputDecision(False, "EMERGENCY", "emergency")
        if not text.strip():
            return InputDecision(False, "EMPTY_INPUT")
        return InputDecision(True)

    def verify(self, answer: str, evidence: tuple[str, ...], branch: str = "default") -> Verdict:
        # Definitive claims stay non-retryable even with absent evidence.
        issues = []
        if _DIAGNOSIS.search(answer):
            issues.append(Issue("DEFINITIVE_DIAGNOSIS", False))
        if not any(text.strip() for text in evidence):
            return Verdict(False, tuple(issues) + (Issue("NO_EVIDENCE", False),))
        if not answer.strip():
            return Verdict(False, (Issue("EMPTY_ANSWER", True),))
        # Inspect each source independently so contraindications cannot cross documents.
        contraindications = set().union(*(_contraindications(text) for text in evidence))
        dropped = contraindications - _contraindications(answer)
        if dropped:
            issues.append(Issue("CONTRAINDICATION_DROPPED", True, len(dropped)))
        unsupported = _doses(answer) - set().union(*(_doses(text) for text in evidence))
        if unsupported:
            issues.append(Issue("UNSUPPORTED_DOSE", True, len(unsupported)))
        return Verdict(not issues, tuple(issues))

    def finalize(self, answer: str, branch: str = "default") -> str:
        return answer.rstrip() + "\n\n" + DISCLAIMER


register("medical", MedicalFilter)
BUILTINS["medical"] = __name__
