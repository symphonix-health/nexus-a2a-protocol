"""Exponential backoff retry."""

from typing import Callable, TypeVar, Optional

T = TypeVar("T")


def retry(fn: Callable[[], T], retries: int, base_delay: float, sleeper: Optional[Callable[[float], None]] = None) -> T:
    if retries <= 0:
        # single attempt, no retries
        return fn()

    import time

    for attempt in range(retries):
        try:
            return fn()
        except Exception:
            # If this was the last allowed attempt, re-raise
            if attempt == retries - 1:
                raise
            delay = base_delay * (2 ** attempt)
            if sleeper is not None:
                sleeper(delay)
            else:
                time.sleep(delay)
