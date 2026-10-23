"""Cancellation and phase reporting shared by every stage of a queued operation."""

from __future__ import annotations

import time
from collections.abc import Callable
from contextvars import ContextVar
from dataclasses import dataclass, field


class OperationCancelled(Exception):
    """The operation stopped cooperatively, including all of its child work."""


@dataclass
class Operation:
    task_id: str
    checkpoint: Callable[[], None]
    phase: Callable[[str, int, int, str | None], None]
    checks: list[Callable[[], None]] = field(default_factory=list)
    finalizers: list[Callable[[str], None]] = field(default_factory=list)


current_operation: ContextVar[Operation | None] = ContextVar("operation", default=None)


def checkpoint() -> None:
    operation = current_operation.get()
    if operation is not None:
        operation.checkpoint()
        for check in operation.checks:
            check()


def report_phase(name: str, completed: int, total: int, detail: str | None = None) -> None:
    checkpoint()
    operation = current_operation.get()
    if operation is not None:
        operation.phase(name, completed, total, detail)


def cooperative_wait(seconds: float) -> None:
    """Rate-limit/backoff waits remain cancellable without interrupting an HTTP call."""
    deadline = time.monotonic() + seconds
    while True:
        checkpoint()
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        time.sleep(min(0.1, remaining))
