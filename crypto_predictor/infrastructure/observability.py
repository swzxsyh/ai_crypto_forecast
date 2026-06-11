"""Lightweight observability primitives."""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    name: str
    fields: dict[str, Any] = field(default_factory=dict)


class EventSink:
    def emit(self, event: Event) -> None:
        logger.info("%s %s", event.name, event.fields)


default_event_sink = EventSink()


@contextmanager
def observed(name: str, **fields: Any) -> Iterator[None]:
    started = time.perf_counter()
    try:
        default_event_sink.emit(Event(name=f"{name}.started", fields=fields))
        yield
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        default_event_sink.emit(Event(name=f"{name}.succeeded", fields={**fields, "elapsed_ms": elapsed_ms}))
    except Exception as exc:
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        default_event_sink.emit(
            Event(name=f"{name}.failed", fields={**fields, "elapsed_ms": elapsed_ms, "error": str(exc)})
        )
        raise
