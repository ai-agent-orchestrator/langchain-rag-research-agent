"""Bounded write retries; search/read paths must not use this helper."""
from __future__ import annotations

MATURITY = "incubating"

import logging
import time

logger = logging.getLogger(__name__)


def transient_write_error(exc):
    if isinstance(exc, OSError):
        return True
    message = str(exc).lower()
    return ("tantivy" in message and "io error" in message
            and any(code in message for code in ("os error 5", "os error 32")))


def retry_io(fn, attempts=4, base_delay=0.2, retry_on=(PermissionError, OSError),
             sleep=time.sleep, on_retry=None, retry_if=None):
    """attempts includes the first call. Return fn's value, re-raise the original last error."""
    if attempts < 1 or base_delay < 0:
        raise ValueError("attempts must be positive and base_delay nonnegative")
    for attempt in range(attempts):
        try:
            return fn()
        except retry_on as exc:
            if attempt + 1 == attempts or (retry_if is not None and not retry_if(exc)):
                raise
            delay = base_delay * 2 ** attempt
            logger.warning("write retry %s/%s after %s (%ss)", attempt + 1, attempts - 1, type(exc).__name__, delay)
            if on_retry is not None:
                on_retry(attempt + 1, exc, delay)
            sleep(delay)
