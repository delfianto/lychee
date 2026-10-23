"""Background task queue — runs long work off the request thread.

Scans, downloads, and syncs are submitted here and run on a worker thread with
its own DB session; lifecycle + progress flow through the ``TaskTracker`` (→ SSE).
So the HTTP handler validates, enqueues, and returns ``202`` with a task id at
once, while the browser follows ``/api/events``. One worker by default keeps
SQLite writers from contending; the request thread only validates + enqueues.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor, wait
from typing import Any

from sqlalchemy.orm import Session, sessionmaker

from src.core.logging import get_logger
from src.core.persistence.database import SessionLocal
from src.tasks.schema import TaskOut
from src.tasks.tracker import TaskInfo, tracker

logger = get_logger(__name__)

ProgressFn = Callable[[int, str], None]
Work = Callable[[Session, ProgressFn], dict[str, Any] | None]


MIN_WORKERS = 1
MAX_WORKERS = 10


def clamp_workers(value: int) -> int:
    return max(MIN_WORKERS, min(MAX_WORKERS, int(value)))


class TaskQueue:
    def __init__(self, *, max_workers: int = 1) -> None:
        self._download_workers = clamp_workers(max_workers)
        self._sync_workers = clamp_workers(max_workers)
        self._download_executor: ThreadPoolExecutor | None = None
        self._sync_executor: ThreadPoolExecutor | None = None
        self._session_factory: sessionmaker[Session] = SessionLocal
        self._futures: set[Future[None]] = set()
        self._lock = threading.Lock()

    @property
    def download_workers(self) -> int:
        return self._download_workers

    @property
    def sync_workers(self) -> int:
        return self._sync_workers

    def set_download_workers(self, count: int) -> int:
        clamped = clamp_workers(count)
        with self._lock:
            if clamped != self._download_workers:
                self._download_workers = clamped
                old, self._download_executor = self._download_executor, None
                if old is not None:
                    old.shutdown(wait=False)
        return self._download_workers

    def set_sync_workers(self, count: int) -> int:
        clamped = clamp_workers(count)
        with self._lock:
            if clamped != self._sync_workers:
                self._sync_workers = clamped
                old, self._sync_executor = self._sync_executor, None
                if old is not None:
                    old.shutdown(wait=False)
        return self._sync_workers

    def configure(self, session_factory: sessionmaker[Session]) -> None:
        """Bind workers to a session factory (tests point this at their temp engine)."""
        self._session_factory = session_factory

    def _executor_for_locked(self, kind: str) -> ThreadPoolExecutor:
        # Separate pools so downloads and sync/scan jobs run simultaneously without
        # blocking one another, and each pool honours its own concurrency setting.
        if kind == "download":
            if self._download_executor is None:
                self._download_executor = ThreadPoolExecutor(
                    max_workers=self._download_workers, thread_name_prefix="lychee-dl"
                )
            return self._download_executor
        if self._sync_executor is None:
            self._sync_executor = ThreadPoolExecutor(
                max_workers=self._sync_workers, thread_name_prefix="lychee-sync"
            )
        return self._sync_executor

    def submit(self, kind: str, label: str, work: Work) -> TaskInfo:
        task = tracker.start(kind, label)
        with self._lock:
            future = self._executor_for_locked(kind).submit(self._run, task, work)
            self._futures = {f for f in self._futures if not f.done()}
            self._futures.add(future)
        return task

    def submit_task(self, kind: str, label: str, work: Work) -> TaskOut:
        """``submit`` for API handlers: enqueue and return the serialisable task."""
        return TaskOut.model_validate(self.submit(kind, label, work))

    def _run(self, task: TaskInfo, work: Work) -> None:
        # expire_on_commit=False: work (esp. downloads) commits repeatedly to expose
        # progress to readers, and must keep using its loaded ORM objects afterward.
        session = self._session_factory(expire_on_commit=False)
        try:
            result = work(session, lambda pct, detail: tracker.progress(task, pct, detail))
            session.commit()
            tracker.finish(task, result=result)
        except Exception as exc:  # noqa: BLE001 - record failure on the task, keep the worker alive
            session.rollback()
            logger.exception("task_failed", task_id=task.id, kind=task.kind)
            tracker.finish(task, error=str(exc))
        finally:
            session.close()

    def wait_idle(self, timeout: float = 30.0) -> None:
        """Block until in-flight work drains (tests + graceful shutdown)."""
        with self._lock:
            pending = list(self._futures)
        _ = wait(pending, timeout=timeout)

    def shutdown(self) -> None:
        with self._lock:
            dl_exec, self._download_executor = self._download_executor, None
            sync_exec, self._sync_executor = self._sync_executor, None
        if dl_exec is not None:
            dl_exec.shutdown(wait=False, cancel_futures=True)
        if sync_exec is not None:
            sync_exec.shutdown(wait=False, cancel_futures=True)


queue = TaskQueue()
