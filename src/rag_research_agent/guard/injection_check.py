"""Opt-in, local injection screening. Evidence is for callers, never auto-logged.

No model or store is needed. Callers must mask inputs first and persist only
``code`` in graph state/events. This heuristic is not a security guarantee.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import html
import re
import unicodedata
from urllib.parse import unquote

MATURITY = "incubating"

__all__ = ["InjectionDecision", "check_user_input", "check_passage"]


@dataclass(frozen=True)
class InjectionDecision:
    allowed: bool
    code: str = ""
    evidence: str = field(default="", repr=False)
    span: tuple[int, int] | None = None


def _compact(text: str) -> str:
    # NFKD unifies fullwidth characters and canonical decomposed Hangul.
    return "".join(c for c in unicodedata.normalize("NFKD", text).casefold()
                   if unicodedata.category(c)[0] in "LN")


def _words(*terms: str) -> str:
    return "(?:" + "|".join(re.escape(_compact(t)) for t in terms) + ")"


_TARGET = _words("이전 지시", "앞선 지시", "기존 지침", "모든 규칙", "시스템 지시", "안전 규칙")
_OVERRIDE = _words("무시해", "무시하라", "무시하고", "무시하세요", "잊어", "폐기해", "따르지 마")
_ACTION = _words("따라", "수행해", "실행해", "답해", "출력해", "무시해", "적용해", "보내")
_SECRET = _words("시스템 프롬프트", "내부 지침", "숨겨진 지시", "내부 정보", "비공개 설정")
_REVEAL = (_words("출력해", "보여줘", "공개해", "알려줘", "그대로 써", "전송해")
           + "(?!" + _words("선", "서는") + ")")
_ROLE = _words("나는 관리자", "나는 개발자", "관리자 명령", "개발자 메시지", "시스템 메시지", "개발자 권한")
_INDIRECT = _words("이 문서를 읽는", "검색 문서 지침", "검색 결과 지시", "문서 내 명령", "인공지능에게", "요약하는 모델")

# Priority: document-origin instructions, impersonation, disclosure, override.
_RULES = (
    ("indirect", re.compile(_INDIRECT + r".{0,100}" + _ACTION)),
    ("role_spoofing", re.compile(_ROLE + r".{0,100}" + _ACTION)),
    ("role_spoofing", re.compile(_words("[system]", "[developer]") + r".{0,70}" + _OVERRIDE)),
    ("exfiltration", re.compile(_SECRET + r".{0,60}" + _REVEAL)),
    ("exfiltration", re.compile(_REVEAL + r".{0,40}" + _SECRET)),
    ("direct_override", re.compile(_TARGET + r".{0,45}" + _OVERRIDE)),
    ("direct_override", re.compile(_words("ignore previous instructions", "ignore all instructions"))),
)
_PASSAGE_RULE = re.compile(
    _words("답변", "요약", "보고서") + r".{0,50}" +
    _words("출처를 삭제해", "근거를 숨겨", "성공이라고만 답해"))
_ANCHORS = ("이전 지시", "무시해", "시스템 프롬프트", "출력해", "관리자 명령", "개발자 메시지")
_ENCODED = re.compile(r"(?:%[0-9a-fA-F]{2})+|&(?:#[xX][0-9a-fA-F]+|#[0-9]+|[a-zA-Z]+);")
_QUOTED_ANALYSIS = re.compile(
    r'''\s*["'“‘「](.+?)["'”’」](?:라는|란|는)\s*'''
    r"(?:문구|표현|문장)(?:의 의미를 설명해 주세요|을 보안 관점에서 분석해 주세요|을 영어로 번역해 주세요)[.!?]?\s*",
    re.DOTALL,
)


def _view(text: str, *, decode: bool) -> tuple[str, list[tuple[int, int]]]:
    chars: list[str] = []
    positions: list[tuple[int, int]] = []

    def append(value: str, start: int, end: int) -> None:
        for char in _compact(value):
            chars.append(char)
            positions.append((start, end))

    cursor = 0
    for match in _ENCODED.finditer(text) if decode else ():
        for index in range(cursor, match.start()):
            append(text[index], index, index + 1)
        token = match.group()
        value = unquote(token, errors="replace") if token.startswith("%") else html.unescape(token)
        append(value, match.start(), match.end())
        cursor = match.end()
    for index in range(cursor, len(text)):
        append(text[index], index, index + 1)
    return "".join(chars), positions


def _check(text: str, *, passage: bool) -> InjectionDecision:
    if not isinstance(text, str):
        raise TypeError("injection input must be str")
    # Narrow quoted-language tasks only; never exempt arbitrary text containing
    # words such as 'research', 'test', or 'security'. Passages are untrusted data.
    if not passage and _QUOTED_ANALYSIS.fullmatch(text):
        return InjectionDecision(True)
    rules = _RULES + ((("indirect", _PASSAGE_RULE),) if passage else ())
    for decoded in (False, True):
        view, positions = _view(text, decode=decoded)
        for kind, rule in rules:
            match = rule.search(view)
            if match is None:
                continue
            start, end = positions[match.start()][0], positions[match.end() - 1][1]
            evidence = text[start:end]
            plain = unicodedata.normalize("NFC", evidence).casefold()
            obfuscated = evidence != unicodedata.normalize("NFKC", evidence) or any(
                _compact(a) in match.group() and a not in plain for a in _ANCHORS)
            if decoded or obfuscated:
                kind = "encoding"
            return InjectionDecision(False, f"INJECTION:{kind}", evidence, (start, end))
    return InjectionDecision(True)


def check_user_input(text: str) -> InjectionDecision:
    """Screen a user request without changing any default DomainFilter behavior."""
    return _check(text, passage=False)


def check_passage(text: str) -> InjectionDecision:
    """Screen one retrieved paragraph, including answer/citation manipulation."""
    return _check(text, passage=True)
