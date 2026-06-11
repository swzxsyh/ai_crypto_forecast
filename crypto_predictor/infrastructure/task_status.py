"""Observable task status store."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock
from typing import Any

from crypto_predictor.time_utils import to_iso, utc_now


@dataclass
class TaskStatus:
    name: str
    state: str
    updated_at: str
    fields: dict[str, Any] = field(default_factory=dict)


class InMemoryTaskStatusStore:
    def __init__(self) -> None:
        self._lock = RLock()
        self._statuses: dict[str, TaskStatus] = {}

    def set(self, name: str, state: str, **fields: Any) -> TaskStatus:
        status = TaskStatus(name=name, state=state, updated_at=to_iso(utc_now()), fields=fields)
        with self._lock:
            self._statuses[name] = status
        return status

    def get(self, name: str) -> TaskStatus | None:
        with self._lock:
            return self._statuses.get(name)

    def all(self) -> list[TaskStatus]:
        with self._lock:
            return list(self._statuses.values())


default_task_status_store = InMemoryTaskStatusStore()
