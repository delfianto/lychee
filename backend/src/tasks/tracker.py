"""In-memory task tracker; each lifecycle change publishes an SSE event.

A task is a unit of long work (a library scan, a chapter download, a sync). The
tracker keeps a bounded recent history for ``GET /api/tasks`` and emits
``<kind>.started`` / ``<kind>.progress`` / ``<kind>.done`` / ``<kind>.failed``
events to the broker so the UI can show live progress.
"""

from __future__ import annotations

import threading
from dataclasses import asdict, dataclass
from typing import Any

from src.core.persistence.base_model import gen_id
from src.tasks.events import broker


@dataclass
class TaskInfo:
    id: str
    kind: str
    label: str
    status: str = "running"  # running | done | failed
    progress: int = 0
    detail: str | None = None
    result: dict[str, Any] | None = None


class TaskTracker:
    def __init__(self, *, keep: int = 50) -> None:
        self._tasks: dict[str, TaskInfo] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._keep = keep

    def _publish(self, info: TaskInfo, event: str) -> None:
        broker.publish({"event": event, "task": asdict(info)})

    def start(self, kind: str, label: str) -> TaskInfo:
        info = TaskInfo(id=gen_id(), kind=kind, label=label)
        with self._lock:
            self._tasks[info.id] = info
            self._order.append(info.id)
            while len(self._order) > self._keep:
                self._tasks.pop(self._order.pop(0), None)
        self._publish(info, f"{kind}.started")
        return info

    def progress(self, info: TaskInfo, pct: int, detail: str | None = None) -> None:
        info.progress = max(0, min(100, pct))
        if detail is not None:
            info.detail = detail
        self._publish(info, f"{info.kind}.progress")

    def finish(
        self, info: TaskInfo, *, error: str | None = None, result: dict[str, Any] | None = None
    ) -> None:
        info.status = "failed" if error else "done"
        if error:
            info.detail = error
        else:
            info.progress = 100
            info.result = result
        self._publish(info, f"{info.kind}.{info.status}")

    def snapshot(self) -> list[TaskInfo]:
        with self._lock:
            return [self._tasks[i] for i in self._order]


tracker = TaskTracker()
