"""Event-gated stress tests against the real bounded thread worker."""
import asyncio
import gc
from threading import Event

import pytest

from rag_research_agent.rag.execution import (
    BoundedWorker,
    InferenceCapacityExceeded,
    InferenceTimeout,
)


async def _until(predicate):
    """Yield to callbacks until a state transition; timeout is only a watchdog."""
    async def observe():
        while not predicate():
            await asyncio.sleep(0)

    await asyncio.wait_for(observe(), timeout=2)


async def _returned(worker, capacity):
    # active alone cannot detect a lost semaphore permit or a leaked waiter.
    await _until(lambda: worker.active == worker.waiting == 0
                 and worker._slots._value == capacity)


async def _cleanup(worker, release, tasks):
    release.set()
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await worker.aclose()


def test_burst_rejects_exact_queue_overflow_and_returns_all_slots():
    async def scenario():
        capacity, waiters, requests = 3, 5, 24
        worker = BoundedWorker(capacity, waiters, admission_timeout=2)
        release = Event()

        def blocking(index):
            assert release.wait(3), "worker release watchdog expired"
            return index

        tasks = [asyncio.create_task(worker.run(blocking, index))
                 for index in range(requests)]
        try:
            overflow = requests - capacity - waiters
            await _until(lambda: worker.active == capacity
                         and worker.waiting == waiters
                         and sum(task.done() for task in tasks) == overflow)
            rejected = [task.exception() for task in tasks if task.done()]
            assert len(rejected) == overflow
            assert all(isinstance(error, InferenceCapacityExceeded) for error in rejected)
            assert worker._slots._value == 0
            release.set()
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=2)
            assert sum(isinstance(result, InferenceCapacityExceeded)
                       for result in results) == overflow
            accepted = [result for result in results if isinstance(result, int)]
            assert len(set(accepted)) == capacity + waiters
            await _returned(worker, capacity)
            assert await worker.run(lambda: "reused") == "reused"
            await _returned(worker, capacity)
        finally:
            await _cleanup(worker, release, tasks)

    asyncio.run(scenario())


def test_response_timeout_holds_slot_until_real_completion_then_admits_waiter():
    async def scenario():
        worker = BoundedWorker(1, 1, admission_timeout=2)
        loop = asyncio.get_running_loop()
        started, release, next_started = asyncio.Event(), Event(), Event()

        def blocking():
            loop.call_soon_threadsafe(started.set)
            assert release.wait(3), "worker release watchdog expired"
            return "late result"

        def following():
            next_started.set()
            return "next result"

        tasks = [asyncio.create_task(worker.run(blocking, timeout=0.02))]
        try:
            await asyncio.wait_for(started.wait(), timeout=2)
            with pytest.raises(InferenceTimeout):
                await asyncio.wait_for(tasks[0], timeout=2)
            assert worker.active == 1
            assert worker._slots._value == 0
            tasks.append(asyncio.create_task(worker.run(following)))
            await _until(lambda: worker.waiting == 1)
            assert not next_started.is_set()
            with pytest.raises(InferenceCapacityExceeded):
                await worker.run(following)
            release.set()
            assert await asyncio.wait_for(tasks[1], timeout=2) == "next result"
            assert next_started.is_set()
            await _returned(worker, 1)
        finally:
            await _cleanup(worker, release, tasks)

    asyncio.run(scenario())


def test_mass_cancellation_reclaims_waiters_and_consumes_late_exceptions(recwarn):
    async def scenario():
        capacity, waiters = 4, 12
        worker = BoundedWorker(capacity, waiters, admission_timeout=2)
        loop = asyncio.get_running_loop()
        release = Event()
        diagnostics = []
        failures = []
        previous_handler = loop.get_exception_handler()
        loop.set_exception_handler(lambda _loop, context: diagnostics.append(context))

        def fail_late():
            assert release.wait(3), "worker release watchdog expired"
            loop.call_soon_threadsafe(failures.append, "raised")
            raise RuntimeError("late worker failure after caller cancellation")

        running = [asyncio.create_task(worker.run(fail_late)) for _ in range(capacity)]
        queued = []
        try:
            await _until(lambda: worker.active == capacity)
            queued = [asyncio.create_task(worker.run(lambda index=index: index))
                      for index in range(waiters)]
            await _until(lambda: worker.waiting == waiters)
            cancelled = running + queued[::2]
            for task in cancelled:
                task.cancel()
            results = await asyncio.wait_for(
                asyncio.gather(*cancelled, return_exceptions=True), timeout=2)
            assert all(isinstance(result, asyncio.CancelledError) for result in results)
            assert worker.active == capacity
            assert worker.waiting == waiters // 2
            assert worker._slots._value == 0
            release.set()
            assert await asyncio.wait_for(
                asyncio.gather(*queued[1::2]), timeout=2) == list(range(1, waiters, 2))
            await _returned(worker, capacity)
            # shutdown waits for all thread callbacks; subsequent loop turns and GC
            # expose unobserved wrapped-future exceptions to the real loop handler.
            await worker.aclose()
            await asyncio.sleep(0)
            assert len(failures) == capacity
            # Drop caller tasks and cancellation tracebacks before forcing GC so
            # retained references cannot conceal an unobserved future exception.
            running.clear()
            queued.clear()
            cancelled.clear()
            results.clear()
            gc.collect()
            await asyncio.sleep(0)
            assert not diagnostics
        finally:
            try:
                await _cleanup(worker, release, running + queued)
            finally:
                loop.set_exception_handler(previous_handler)

    asyncio.run(scenario(), debug=True)
    assert not recwarn.list


def test_aclose_waits_for_running_work_and_rejects_queued_and_new_work():
    async def scenario():
        worker = BoundedWorker(1, 1, admission_timeout=2)
        loop = asyncio.get_running_loop()
        started, release = asyncio.Event(), Event()
        queued_started = Event()

        def blocking():
            loop.call_soon_threadsafe(started.set)
            assert release.wait(3), "worker release watchdog expired"
            return 42

        tasks = [asyncio.create_task(worker.run(blocking))]
        try:
            await asyncio.wait_for(started.wait(), timeout=2)
            tasks.append(asyncio.create_task(worker.run(queued_started.set)))
            await _until(lambda: worker.waiting == 1)
            closing = asyncio.create_task(worker.aclose())
            tasks.append(closing)
            await _until(lambda: worker._closed)
            assert not closing.done()
            assert worker.active == 1
            assert worker.waiting == 1
            with pytest.raises(RuntimeError, match="worker is closed"):
                await worker.run(queued_started.set)
            release.set()
            assert await asyncio.wait_for(tasks[0], timeout=2) == 42
            with pytest.raises(RuntimeError, match="worker is closed"):
                await asyncio.wait_for(tasks[1], timeout=2)
            await asyncio.wait_for(closing, timeout=2)
            assert not queued_started.is_set()
            await _returned(worker, 1)
        finally:
            await _cleanup(worker, release, tasks)

    asyncio.run(scenario())
