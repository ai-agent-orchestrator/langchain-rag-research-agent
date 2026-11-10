"""Optional canonical legal-intake package adapter. No masking rules are copied here."""
from __future__ import annotations

MATURITY = "incubating"

from rag_research_agent.guard.protocols import PolicyDecision


class IntakeGuardUnavailable(RuntimeError):
    pass


def _package():
    try:
        import intake_guard
        return intake_guard
    except ImportError as exc:
        raise IntakeGuardUnavailable("intake-guard 미설치: pip install -e C:\\work\\legal-intake-guard\\packages\\intake_guard") from exc


class IntakeMasker:
    def __init__(self):
        self.package = _package()

    def mask(self, text):
        result = self.package.mask_personal_data(text)
        if result.decision == self.package.Decision.ALLOW:
            return text
        if result.decision == self.package.Decision.TRANSFORM and isinstance(result.safe_text, str):
            return result.safe_text
        raise RuntimeError("intake-guard returned an invalid masking decision")


class IntakeInputPolicy:
    def __init__(self, profile="research"):
        self.package, self.profile = _package(), profile

    def check(self, text):
        result = self.package.check_input_policy(text, profile=self.profile)
        return PolicyDecision(result.decision == self.package.Decision.ALLOW, result.reason_code)


class IntakeOutputPolicy:
    def __init__(self, profile="research"):
        self.package, self.profile = _package(), profile

    def check(self, text):
        result = self.package.check_output_policy(text, profile=self.profile)
        return PolicyDecision(result.decision == self.package.Decision.ALLOW, result.reason_code)
