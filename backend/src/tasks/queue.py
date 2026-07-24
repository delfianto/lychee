"""Background task queue — runs long work off the request thread (ADR 08/15).

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
from src.tasks.tracker import TaskInfo, tracker

logger = get_logger(__name__)

ProgressFn = Callable[[int, str], None]
Work = Callable[[Session, ProgressFn], dict[str, Any] | None]


class TaskQueue:
    def __init__(self, *, max_workers: int = 1) -> None:
        self._max_workers = max_workers
        self._executor: ThreadPoolExecutor | None = None
        self._session_factory: sessionmaker[Session] = SessionLocal
        self._futures: set[Future[None]] = set()
        self._lock = threading.Lock()

    def configure(self, session_factory: sessionmaker[Session]) -> None:
        """Bind workers to a session factory (tests point this at their temp engine)."""
        self._session_factory = session_factory

    def _executor_locked(self) -> ThreadPoolExecutor:
        # Lazily (re)create so the queue survives app restarts within one process
        # (the test suite starts the app many times, each shutting the pool down).
        if self._executor is None:
            self._executor = ThreadPoolExecutor(
                max_workers=self._max_workers, thread_name_prefix="lychee-task"
            )
        return self._executor

    def submit(self, kind: str, label: str, work: Work) -> TaskInfo:
        task = tracker.start(kind, label)
        with self._lock:
            future = self._executor_locked().submit(self._run, task, work)
            self._futures = {f for f in self._futures if not f.done()}
            self._futures.add(future)
        return task

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
            executor, self._executor = self._executor, None
        if executor is not None:
            executor.shutdown(wait=False, cancel_futures=True)


queue = TaskQueue()
