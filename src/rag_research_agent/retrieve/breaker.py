"""Circuit breaker for retrieval calls (N6). Stdlib only; not wired into any pipeline yet.

closed    -> calls pass through; consecutive RetrievalUnavailable failures are counted.
open      -> calls fail fast with RetrievalUnavailable("circuit open") until the cooldown ends.
half-open -> exactly one trial call is let through; success closes, failure re-opens.

Only RetrievalUnavailable counts as a failure. Any other exception is a programming error: it is
re-raised unchanged and never moves the breaker. State-change callbacks receive state names and
counts only, never query text or exception messages.
"""
from __future__ import annotations

MATURITY = "incubating"

from dataclasses import dataclass
import math
from threading import Lock
import time
from typing import Callable

from rag_research_agent.core.contracts import RetrievalUnavailable

CLOSED, OPEN, HALF_OPEN = "closed", "open", "half_open"


class CircuitOpen(RetrievalUnavailable):
    """Raised without calling the backend while the breaker is open (still maps to 503)."""
    code = "RETRIEVAL_UNAVAILABLE"


@dataclass(frozen=True)
class BreakerEvent:
    previous: str
    current: str
    consecutive_failures: int


class CircuitBreaker:
    def __init__(self, failure_threshold: int = 5, cooldown_s: float = 30.0, *,
                 clock: Callable[[], float] = time.monotonic,
                 on_change: Callable[[BreakerEvent], None] | None = None):
        if failure_threshold < 1:
            raise ValueError("failure_threshold must be >= 1")
        if not math.isfinite(cooldown_s) or cooldown_s <= 0:
            raise ValueError("cooldown_s must be positive and finite")
        self.failure_threshold, self.cooldown_s = failure_threshold, cooldown_s
        self._clock, self._on_change = clock, on_change
        self._lock = Lock()
        self._state = CLOSED
        self._failures = 0
        self._opened_at = 0.0
        self._trial_running = False

    @property
    def state(self) -> str:
        with self._lock:
            events = self._refresh()
            state = self._state
        self._emit(events)
        return state

    @property
    def consecutive_failures(self) -> int:
        with self._lock:
            return self._failures

    def call(self, function: Callable, *args, **kwargs):
        trial = self._admit()
        try:
            result = function(*args, **kwargs)
        except RetrievalUnavailable:
            self._record(success=False, trial=trial)
            raise
        except BaseException:
            # Not a retrieval failure: counters stay as they are, but a half-open trial slot is freed.
            if trial:
                with self._lock:
                    self._trial_running = False
            raise
        self._record(success=True, trial=trial)
        return result

    # -- internals. State changes are collected under the lock and emitted after releasing it.
    def _admit(self) -> bool:
        with self._lock:
            events = self._refresh()
            state, busy = self._state, self._trial_running
            if state == HALF_OPEN and not busy:
                self._trial_running = True
        self._emit(events)
        if state == CLOSED:
            return False
        if state == OPEN:
            raise CircuitOpen("retrieval circuit open")
        if busy:
            raise CircuitOpen("retrieval circuit half-open; trial in progress")
        return True

    def _record(self, *, success: bool, trial: bool):
        events = []
        with self._lock:
            if trial:
                self._trial_running = False
            if success:
                if self._state != CLOSED:
                    events.append(self._move(CLOSED))
                self._failures = 0
            else:
                self._failures += 1
                if self._state == HALF_OPEN or (self._state == CLOSED and self._failures >= self.failure_threshold):
                    self._opened_at = self._clock()
                    events.append(self._move(OPEN))
        self._emit(events)

    def _refresh(self) -> list[BreakerEvent]:
        if self._state == OPEN and self._clock() - self._opened_at >= self.cooldown_s:
            return [self._move(HALF_OPEN)]
        return []

    def _move(self, new_state: str) -> BreakerEvent:
        event = BreakerEvent(self._state, new_state, self._failures)
        self._state = new_state
        return event

    def _emit(self, events: list[BreakerEvent]):
        if self._on_change is not None:
            for event in events:
                self._on_change(event)
