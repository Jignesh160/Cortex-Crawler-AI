"""Tiny retry/backoff helper for transient failures (network, throttling)."""
from __future__ import annotations

import functools
import random
import time
from typing import Callable, TypeVar

from .log import get_logger

_log = get_logger("retry")
T = TypeVar("T")


def with_retry(
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator: retry with exponential backoff + jitter on `exceptions`."""
    def deco(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            delay = base_delay
            last: BaseException | None = None
            for i in range(1, attempts + 1):
                try:
                    return fn(*args, **kwargs)
                except exceptions as exc:  # noqa: PERF203
                    last = exc
                    if i == attempts:
                        break
                    sleep = min(max_delay, delay) + random.uniform(0, delay / 2)
                    _log.warning("attempt %d/%d failed: %s; retrying in %.1fs",
                                 i, attempts, exc, sleep)
                    time.sleep(sleep)
                    delay *= 2
            assert last is not None
            raise last
        return wrapper
    return deco
