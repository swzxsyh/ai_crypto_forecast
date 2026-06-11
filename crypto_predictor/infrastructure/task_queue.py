"""Task queue abstraction with a local thread implementation."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


TaskFn = Callable[..., Any]


@dataclass(frozen=True)
class SubmittedTask:
    task_id: str


class TaskQueue(Protocol):
    def submit(self, name: str, func: TaskFn, *args: Any, **kwargs: Any) -> SubmittedTask:
        ...


class LocalThreadQueue:
    def __init__(self) -> None:
        self._counter = 0

    def submit(self, name: str, func: TaskFn, *args: Any, **kwargs: Any) -> SubmittedTask:
        self._counter += 1
        task_id = f"local-{self._counter}"
        thread = threading.Thread(target=func, name=name, args=args, kwargs=kwargs, daemon=True)
        thread.start()
        return SubmittedTask(task_id=task_id)
