"""LAB: semantic prompt-injection signal next to the fixed (regex) guard.

Two layers: the fixed guard decides BLOCK with an explainable rule; this layer compares the
input to embedded attack exemplars and can only raise REVIEW. It never blocks on its own and
never adds session risk. Inputs are split into sentences so one attack line hidden in a long
benign text is still compared on its own.

Promotion requires a labelled set of attacks and benign legal questions (e.g. "I was accused of
forging evidence") with the false-review rate measured at a calibrated threshold.
"""
from __future__ import annotations

MATURITY = "lab"

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable, Sequence

Encode = Callable[[Sequence[str]], list[list[float]]]


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"[​-‏﻿]", "", text)


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?。])\s+|\n+", normalize(text))
    return [p.strip() for p in parts if p.strip()]


@dataclass(frozen=True)
class SemanticSignal:
    decision: str            # "ALLOW" | "REVIEW"
    score: float
    exemplar_id: str | None
    sentence_index: int | None
    threshold_version: str


class SemanticGuard:
    def __init__(self, encode: Encode, exemplars: dict[str, str], threshold: float, threshold_version: str):
        if not exemplars:
            raise ValueError("at least one attack exemplar is required")
        self._encode, self.threshold, self.version = encode, threshold, threshold_version
        self._ids = list(exemplars)
        self._vectors = encode([normalize(exemplars[i]) for i in self._ids])

    def check(self, text: str) -> SemanticSignal:
        parts = sentences(text)
        if not parts:
            return SemanticSignal("ALLOW", 0.0, None, None, self.version)
        best = (-2.0, None, None)
        for index, vec in enumerate(self._encode(parts)):
            for ex_id, ex_vec in zip(self._ids, self._vectors):
                score = sum(a * b for a, b in zip(vec, ex_vec))
                if score > best[0]:
                    best = (score, ex_id, index)
        score, ex_id, index = best
        decision = "REVIEW" if score >= self.threshold else "ALLOW"
        return SemanticSignal(decision, score, ex_id, index, self.version)
