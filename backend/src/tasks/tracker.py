"""In-memory task tracker; each lifecycle change publishes an SSE event.

A task is a unit of long work (a library scan, a chapter download, a sync). The
tracker keeps a bounded recent history for ``GET /api/tasks`` and emits
``<kind>.started`` / ``<kind>.progress`` / ``<kind>.done`` / ``<kind>.failed``
events to the broker so the UI can show live progress.
"""

from __future__ import annotations

import threading
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from typing import Any

from src.core.persistence.base_model import gen_id
from src.tasks.context import OperationCancelled
from src.tasks.events import broker


@dataclass
class TaskInfo:
    id: str
    kind: str
    label: str
    status: str = "queued"  # queued | running | cancelling | cancelled | done | failed
    progress: int = 0
    detail: str | None = None
    result: dict[str, Any] | None = None
    phases: dict[str, dict[str, int]] = field(default_factory=dict)


class TaskTracker:
    def __init__(self, *, keep: int = 50) -> None:
        self._tasks: dict[str, TaskInfo] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._keep = keep
        self._cancelled: set[str] = set()

    def _publish(self, info: TaskInfo, event: str) -> None:
        with self._lock:
            payload = asdict(info)
        broker.publish({"event": event, "task": payload})

    def start(self, kind: str, label: str) -> TaskInfo:
        info = TaskInfo(id=gen_id(), kind=kind, label=label)
        with self._lock:
            self._tasks[info.id] = info
            self._order.append(info.id)
            finished = [
                i for i in self._order if self._tasks[i].status in {"done", "failed", "cancelled"}
            ]
            for old_id in finished[: max(0, len(self._order) - self._keep)]:
                self._tasks.pop(old_id, None)
                self._order.remove(old_id)
                self._cancelled.discard(old_id)
        self._publish(info, f"{kind}.started")
        return info

    def cancel(self, task_id: str) -> bool:
        with self._lock:
            info = self._tasks.get(task_id)
            if info is None:
                return False
            if info.status in {"queued", "running", "cancelling"}:
                self._cancelled.add(task_id)
                info.status = "cancelling"
        self._publish(info, f"{info.kind}.progress")
        return True

    def checkpoint(self, task_id: str) -> None:
        with self._lock:
            if task_id in self._cancelled:
                raise OperationCancelled("Cancelled")

    def phase(
        self, info: TaskInfo, name: str, completed: int, total: int, detail: str | None
    ) -> None:
        with self._lock:
            info.phases[name] = {"completed": completed, "total": total}
            if detail is not None:
                info.detail = detail
        self._publish(info, f"{info.kind}.progress")

    def progress(self, info: TaskInfo, pct: int, detail: str | None = None) -> None:
        info.progress = max(0, min(99, pct))
        if detail is not None:
            info.detail = detail
        self._publish(info, f"{info.kind}.progress")

    def finish(
        self,
        info: TaskInfo,
        *,
        error: str | None = None,
        result: dict[str, Any] | None = None,
        cancelled: bool = False,
    ) -> None:
        info.status = "cancelled" if cancelled else "failed" if error else "done"
        if cancelled:
            info.detail = "Cancelled"
        elif error:
            info.detail = error
        else:
            info.progress = 100
            info.result = result
        self._publish(info, f"{info.kind}.{info.status}")

    def snapshot(self) -> list[TaskInfo]:
        with self._lock:
            return deepcopy([self._tasks[i] for i in self._order])


tracker = TaskTracker()
