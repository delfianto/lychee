"""Persist queue limits before applying them; restore before startup recovery."""

from threading import Lock
from typing import Literal

from sqlalchemy.orm import Session

from src.tasks.models import TaskQueueConfig
from src.tasks.queue import queue

_configuration_lock = Lock()


def _apply(row: TaskQueueConfig | None) -> None:
    queue.set_download_workers(row.download_workers if row else 1)
    queue.set_sync_workers(row.sync_workers if row else 1)


def restore_queue(session: Session) -> None:
    with _configuration_lock:
        _apply(session.get(TaskQueueConfig, "default", populate_existing=True))


def save_queue_workers(session: Session, kind: Literal["download", "sync"], count: int) -> None:
    # Serialize read/modify/write/apply across both settings. Simultaneous first
    # saves create one row and never overwrite the other setting with a stale read.
    with _configuration_lock:
        row = session.get(TaskQueueConfig, "default", populate_existing=True)
        if row is None:
            row = TaskQueueConfig(
                id="default",
                download_workers=queue.download_workers,
                sync_workers=queue.sync_workers,
            )
            session.add(row)
        if kind == "download":
            row.download_workers = count
        else:
            row.sync_workers = count
        session.commit()
        _apply(row)
