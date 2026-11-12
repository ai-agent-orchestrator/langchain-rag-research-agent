"""Opt-in local administration rules for explicit, synthetic evidence formats.

No regulation lookup or model is performed here. Import before get_filter("local_admin").
"""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass
from datetime import date
import re

from rag_research_agent.guard.domain_filter import BUILTINS, InputDecision, Issue, Verdict, register

VERSION = "local-admin-filter/1"
NOTICE = "신청 전 담당 기관 확인이 필요합니다."
_CLAUSE = re.compile(r"(?<=[.!?。])\s+|[\n;]+")
_VERSION = re.compile(r"(양식|서식|기준)\s*(?:v|버전\s*)\s*(\d+)(?!\d|\.\d)", re.I)
_DATE = re.compile(r"(?<!\d)(\d{4})(?:-|년\s*)(\d{1,2})(?:-|월\s*)(\d{1,2})(?:일)?(?!\d)")
_EXCEPTION = re.compile(r"(?:지역\s*예외|[가-힣]+[시군구]\s*예외|다만)\s*[:：]?\s*([^:：\s].*)")
_CHECKLIST = re.compile(r"필수\s*구비서류\s*[:：]\s*(.*)")
_BULLET = re.compile(r"^\s*[-*•]\s+(.+)")
_TYPES = (("closure", ("폐업",)), ("renewal", ("갱신",)),
          ("change", ("변경",)), ("permit", ("허가",)),
          ("registration", ("등록", "신고")), ("application", ("신청",)))


def _normal(text: str) -> str:
    return re.sub(r"\s+", "", text).rstrip(".!?。")


def _kind(text: str) -> str:
    return "양식" if text == "서식" else text


def _versions(clause: str) -> set[tuple[str, str, int]]:
    values = {(_kind(m[1]), "revision", int(m[2])) for m in _VERSION.finditer(clause)}
    kinds = {_kind(k) for k in re.findall(r"양식|서식|기준", clause)}
    for match in _DATE.finditer(clause):
        try:
            ordinal = date(*(int(n) for n in match.groups())).toordinal()
        except ValueError:
            continue
        values.update((kind, "date", ordinal) for kind in kinds)
    return values


def _outdated(answer: str, evidence: tuple[str, ...]) -> int:
    latest: dict[tuple[str, str], int] = {}
    for text in evidence:
        for clause in _CLAUSE.split(text):
            if "개정" in clause or "시행일" in clause:
                for kind, scale, value in _versions(clause):
                    key = (kind, scale)
                    latest[key] = max(value, latest.get(key, value))
    old = {entry for clause in _CLAUSE.split(answer) for entry in _versions(clause)
           if entry[2] < latest.get(entry[:2], entry[2])}
    # Explicit old-form advice is also detectable without a numeric version.
    old_markers = set()
    if latest:
        for clause in _CLAUSE.split(answer):
            for match in re.finditer(r"(?:구|이전\s*)(양식|서식|기준)", clause):
                kind = _kind(match[1])
                if any(key[0] == kind for key in latest):
                    old_markers.add(kind)
    return len(old) + len(old_markers)


def _exceptions(text: str) -> set[str]:
    return {_normal(m[1]) for clause in _CLAUSE.split(text)
            if (m := _EXCEPTION.search(clause)) and _normal(m[1])}


def _checklist(text: str) -> set[str]:
    items = set()
    active = False
    for line in text.splitlines():
        header = _CHECKLIST.search(line)
        bullet = _BULLET.match(line) if active else None
        if header:
            active = True
            payload = header[1]
        elif bullet:
            payload = bullet[1]
        else:
            active = False
            continue
        # A checklist ends at sentence punctuation/semicolon, never another clause.
        payload = re.split(r"[.!?。;]", payload, maxsplit=1)[0]
        items.update(_normal(item) for item in re.split(r"[,，·]+", payload) if _normal(item))
    return items


@dataclass(frozen=True)
class LocalAdminFilter:
    name: str = "local_admin"
    version: str = VERSION
    # Fictional defaults; codes rather than input text are returned in branch.
    jurisdictions: tuple[tuple[str, str], ...] = (("가람시", "garam"), ("누리군", "nuri"), ("다온구", "daon"))

    def check_input(self, text: str) -> InputDecision:
        if not text.strip():
            return InputDecision(False, "EMPTY_INPUT")
        matches = {code for keyword, code in self.jurisdictions if keyword in text}
        if not matches:
            return InputDecision(False, "JURISDICTION_REQUIRED")
        if len(matches) > 1:
            return InputDecision(False, "JURISDICTION_AMBIGUOUS")
        application = next((code for code, words in _TYPES if any(word in text for word in words)), "other")
        return InputDecision(True, branch=f"{next(iter(matches))}:{application}")

    def verify(self, answer: str, evidence: tuple[str, ...], branch: str = "default") -> Verdict:
        if not any(text.strip() for text in evidence):
            return Verdict(False, (Issue("NO_EVIDENCE", False),))
        if not answer.strip():
            return Verdict(False, (Issue("EMPTY_ANSWER", True),))
        issues = []
        outdated = _outdated(answer, evidence)
        if outdated:
            issues.append(Issue("OUTDATED_FORM", True, outdated))
        normalized = _normal(answer)
        exceptions = set().union(*(_exceptions(text) for text in evidence))
        dropped = sum(exception not in normalized for exception in exceptions)
        if dropped:
            issues.append(Issue("LOCAL_EXCEPTION_DROPPED", True, dropped))
        checklist = set().union(*(_checklist(text) for text in evidence))
        missing = sum(item not in normalized for item in checklist)
        if missing:
            issues.append(Issue("CHECKLIST_INCOMPLETE", True, missing))
        return Verdict(not issues, tuple(issues))

    def finalize(self, answer: str, branch: str = "default") -> str:
        return answer.rstrip() + "\n\n" + NOTICE


register("local_admin", LocalAdminFilter)
BUILTINS["local_admin"] = __name__
