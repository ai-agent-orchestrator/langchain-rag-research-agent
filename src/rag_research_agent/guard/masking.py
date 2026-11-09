"""Minimal pattern masking for the synthetic learning stage only.

This is NOT the S1 `mask_personal_data` action. It covers resident ID, e-mail and phone
patterns (the same three the recovery snapshot used) and does not detect names or addresses.
Real intake data must not reach RAG until S1 is complete.
"""

MATURITY = "incubating"
import re

MASKING_VERSION = "learning-patterns-v1"

_PATTERNS = (
    ("ID_NUMBER", re.compile(r"(?<!\d)\d{6}[- ]?[1-8]\d{6}(?!\d)")),
    ("EMAIL", re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")),
    ("PHONE", re.compile(r"(?<!\d)(?:\+82[- .]?)?0?1[016789][- .]?\d{3,4}[- .]?\d{4}(?!\d)"
                         r"|(?<!\d)0[2-6]\d?[- .]\d{3,4}[- .]\d{4}(?!\d)")),
)


def mask_pii(text: str) -> str:
    for label, pattern in _PATTERNS:
        text = pattern.sub(f"[{label}]", text)
    return text


def contains_pii(text: str) -> bool:
    return any(pattern.search(text) for _, pattern in _PATTERNS)
