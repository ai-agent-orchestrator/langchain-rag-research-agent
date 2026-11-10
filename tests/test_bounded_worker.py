import asyncio
from threading import Event

import pytest
from rag_research_agent.rag.execution import BoundedWorker, InferenceCapacityExceeded, InferenceTimeout


@pytest.mark.parametrize("abandon", ["timeout", "cancel"])
def test_slot_is_held_until_the_worker_really_finishes(abandon):
    async def run():
        worker = BoundedWorker(concurrent=1, waiters=0)
        started, release = Event(), Event()
        def blocking():
            started.set()
            assert release.wait(5), "test did not release its worker"
            return 42
        task = asyncio.create_task(worker.run(blocking, timeout=0.02 if abandon == "timeout" else None))
        try:
            assert await asyncio.to_thread(started.wait, 2)
            if abandon == "cancel":
                task.cancel()
            with pytest.raises(InferenceTimeout if abandon == "timeout" else asyncio.CancelledError):
                await task
            assert worker.active == 1
            with pytest.raises(InferenceCapacityExceeded):
                await worker.run(lambda: "must not run")
        finally:
            release.set()
            await worker.aclose()
        assert worker.active == 0
    asyncio.run(run())


def test_original_worker_exception_and_subsequent_slot_are_preserved():
    async def run():
        error = RuntimeError("synthetic worker failure")
        async with BoundedWorker() as worker:
            def failing():
                raise error
            with pytest.raises(RuntimeError) as caught:
                await worker.run(failing)
            assert caught.value is error
            assert await worker.run(lambda: 42) == 42
    asyncio.run(run())
