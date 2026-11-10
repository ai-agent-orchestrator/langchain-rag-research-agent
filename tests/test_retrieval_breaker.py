"""N6: circuit breaker state machine, with an injected clock (no sleeping)."""
import threading

import pytest

from rag_research_agent.core.contracts import RetrievalUnavailable
from rag_research_agent.retrieve.breaker import CLOSED, HALF_OPEN, OPEN, CircuitBreaker, CircuitOpen


class Clock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


def down():
    raise RetrievalUnavailable("backend down")


def make(threshold=3, cooldown=10.0):
    clock, events = Clock(), []
    breaker = CircuitBreaker(threshold, cooldown, clock=clock, on_change=events.append)
    return breaker, clock, events


def trip(breaker, times):
    for _ in range(times):
        with pytest.raises(RetrievalUnavailable):
            breaker.call(down)


def test_opens_after_threshold_consecutive_failures_and_fails_fast():
    breaker, _, events = make(threshold=3)
    trip(breaker, 2)
    assert breaker.state == CLOSED and breaker.consecutive_failures == 2
    trip(breaker, 1)
    assert breaker.state == OPEN
    calls = []
    with pytest.raises(CircuitOpen):
        breaker.call(lambda: calls.append(1))
    assert calls == []                              # backend not touched while open
    assert isinstance(CircuitOpen("x"), RetrievalUnavailable)   # still the 503 class
    assert [(e.previous, e.current) for e in events] == [(CLOSED, OPEN)]


def test_success_resets_the_consecutive_count():
    breaker, _, _ = make(threshold=3)
    trip(breaker, 2)
    assert breaker.call(lambda: "ok") == "ok"
    trip(breaker, 2)
    assert breaker.state == CLOSED and breaker.consecutive_failures == 2


def test_other_exceptions_pass_through_and_are_not_counted():
    breaker, _, _ = make(threshold=1)
    with pytest.raises(KeyError):
        breaker.call(lambda: {}["missing"])
    assert breaker.state == CLOSED and breaker.consecutive_failures == 0


def test_cooldown_boundary_then_half_open_success_closes():
    breaker, clock, events = make(threshold=1, cooldown=10.0)
    trip(breaker, 1)
    clock.now = 9.999
    assert breaker.state == OPEN
    clock.now = 10.0
    assert breaker.state == HALF_OPEN
    assert breaker.call(lambda: 42) == 42
    assert breaker.state == CLOSED and breaker.consecutive_failures == 0
    assert [(e.previous, e.current) for e in events] == [(CLOSED, OPEN), (OPEN, HALF_OPEN), (HALF_OPEN, CLOSED)]


def test_half_open_failure_reopens_for_a_new_cooldown():
    breaker, clock, _ = make(threshold=1, cooldown=10.0)
    trip(breaker, 1)
    clock.now = 10.0
    trip(breaker, 1)                                # the single trial fails
    assert breaker.state == OPEN
    clock.now = 19.0
    assert breaker.state == OPEN                    # cooldown restarted at t=10
    clock.now = 20.0
    assert breaker.state == HALF_OPEN


def test_half_open_lets_exactly_one_trial_through_concurrently():
    breaker, clock, _ = make(threshold=1, cooldown=1.0)
    trip(breaker, 1)
    clock.now = 1.0
    entered, release = threading.Event(), threading.Event()

    def slow_trial():
        entered.set()
        release.wait(5)
        return "trial"

    results = []
    worker = threading.Thread(target=lambda: results.append(breaker.call(slow_trial)))
    worker.start()
    assert entered.wait(5)
    with pytest.raises(CircuitOpen):                # second caller while the trial is running
        breaker.call(lambda: "second")
    release.set()
    worker.join(5)
    assert results == ["trial"] and breaker.state == CLOSED


def test_programming_error_during_trial_frees_the_trial_slot():
    breaker, clock, _ = make(threshold=1, cooldown=1.0)
    trip(breaker, 1)
    clock.now = 1.0
    with pytest.raises(ZeroDivisionError):
        breaker.call(lambda: 1 / 0)
    assert breaker.state == HALF_OPEN               # not counted, still waiting for a real trial
    assert breaker.call(lambda: "ok") == "ok"


def test_many_threads_count_failures_exactly():
    breaker, _, _ = make(threshold=1000)
    barrier = threading.Barrier(8)

    def hammer():
        barrier.wait(5)
        for _ in range(50):
            try:
                breaker.call(down)
            except RetrievalUnavailable:
                pass

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(10)
    assert breaker.consecutive_failures == 400 and breaker.state == CLOSED


def test_events_carry_no_text():
    breaker, _, events = make(threshold=1)
    with pytest.raises(RetrievalUnavailable):
        breaker.call(lambda: (_ for _ in ()).throw(RetrievalUnavailable("홍길동 010-1234-5678")))
    assert events and all(set(vars(e)) == {"previous", "current", "consecutive_failures"} for e in events)


@pytest.mark.parametrize("threshold,cooldown", [(0, 1.0), (1, 0.0), (1, float("inf")), (1, float("nan"))])
def test_invalid_settings_are_rejected(threshold, cooldown):
    with pytest.raises(ValueError):
        CircuitBreaker(threshold, cooldown)
