"""Retry helpers for network-heavy integrations."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar


T = TypeVar("T")


def retry_call(
    func: Callable[[], T],
    *,
    attempts: int = 3,
    initial_delay_seconds: float = 0.5,
    backoff: float = 2.0,
    retry_exceptions: tuple[type[BaseException], ...] = (Exception,),
) -> T:
    last_exc: BaseException | None = None
    delay = initial_delay_seconds
    for attempt in range(max(1, attempts)):
        try:
            return func()
        except retry_exceptions as exc:
            last_exc = exc
            if attempt >= attempts - 1:
                break
            time.sleep(max(0.0, delay))
            delay *= backoff
    assert last_exc is not None
    raise last_exc
