"""Masking / input-policy protocols. The canonical implementation lives in legal-intake (decision D3)."""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str = ""


class Masker(Protocol):
    def mask(self, text: str) -> str: ...


class InputPolicy(Protocol):
    def check(self, text: str) -> PolicyDecision: ...


class FakeMasker:
    """Test stand-in. Not a real masker."""
    def mask(self, text: str) -> str:
        return text


class FakeInputPolicy:
    """Blocks only texts containing the marker `[BLOCK]`. Test stand-in."""
    def check(self, text: str) -> PolicyDecision:
        return PolicyDecision(False, "fake_block") if "[BLOCK]" in text else PolicyDecision(True)
