"""Dedicated bounded workers. Abandoning an await never frees a running worker's slot."""
from __future__ import annotations

MATURITY = "incubating"

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
import math
from threading import Lock


class InferenceCapacityExceeded(RuntimeError):
    code = "GENERATION_CAPACITY_EXCEEDED"


class InferenceTimeout(TimeoutError):
    code = "INFERENCE_TIMEOUT"


class BoundedWorker:
    def __init__(self, concurrent=1, waiters=4, admission_timeout=1.0):
        if concurrent < 1 or waiters < 0 or not math.isfinite(admission_timeout) or admission_timeout <= 0:
            raise ValueError("invalid worker limits")
        self._executor = ThreadPoolExecutor(max_workers=concurrent, thread_name_prefix="rra-inference")
        self._slots = asyncio.Semaphore(concurrent)
        self._lock = Lock()
        self._loop = None
        self._active = 0
        self._waiting = 0
        self._closed = False
        self.max_waiters, self.admission_timeout = waiters, admission_timeout

    @property
    def active(self):
        with self._lock:
            return self._active

    @property
    def waiting(self):
        return self._waiting

    async def run(self, function, *args, timeout=None, **kwargs):
        if timeout is not None and (not math.isfinite(timeout) or timeout <= 0):
            raise ValueError("timeout must be positive and finite")
        loop = asyncio.get_running_loop()
        if self._closed:
            raise RuntimeError("worker is closed")
        if self._loop is not None and self._loop is not loop:
            raise RuntimeError("use a worker in one event loop only")
        self._loop = loop
        waiting = self._slots.locked()
        if waiting and self._waiting >= self.max_waiters:
            raise InferenceCapacityExceeded("worker queue is full")
        if waiting:
            self._waiting += 1
        try:
            try:
                if waiting:
                    await asyncio.wait_for(self._slots.acquire(), timeout=self.admission_timeout)
                else:
                    # Acquire without scheduling a child task so simultaneous callers cannot
                    # all observe an available slot and bypass the bounded waiter count.
                    await self._slots.acquire()
            except TimeoutError:
                raise InferenceCapacityExceeded("worker admission timed out") from None
        finally:
            if waiting:
                self._waiting -= 1
        if self._closed:
            self._slots.release()
            raise RuntimeError("worker is closed")
        with self._lock:
            self._active += 1
        def release(_future):
            with self._lock:
                self._active -= 1
            if not loop.is_closed():
                loop.call_soon_threadsafe(self._slots.release)
        try:
            future = self._executor.submit(copy_context().run, function, *args, **kwargs)
        except BaseException:
            release(None)
            raise
        future.add_done_callback(release)
        wrapped = asyncio.wrap_future(future, loop=loop)
        # Consume late errors after a caller timeout/cancellation without changing what awaits see.
        wrapped.add_done_callback(lambda done: None if done.cancelled() else done.exception())
        try:
            return await asyncio.wait_for(asyncio.shield(wrapped), timeout=timeout)
        except TimeoutError:
            if wrapped.done():
                return wrapped.result()  # Preserve a TimeoutError raised by the function itself.
            raise InferenceTimeout("response timed out; worker slot remains held until completion") from None

    async def aclose(self):
        self._closed = True
        await asyncio.to_thread(self._executor.shutdown, wait=True, cancel_futures=False)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self.aclose()
