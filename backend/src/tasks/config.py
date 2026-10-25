"""Persist queue limits before applying them; restore before startup recovery."""

from threading import Lock
from typing import Literal

from sqlalchemy.orm import Session

from src.media import processing
from src.media.models import ImageProcessingConfig
from src.tasks.models import TaskQueueConfig
from src.tasks.queue import queue
from src.tasks.schema import WorkerSettingsOut, WorkerSettingsUpdate

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


def get_worker_settings(session: Session) -> WorkerSettingsOut:
    return WorkerSettingsOut(
        download_workers=queue.download_workers,
        scan_metadata_workers=queue.sync_workers,
        **processing.get_processing(session).model_dump(),
    )


def save_worker_settings(session: Session, data: WorkerSettingsUpdate) -> WorkerSettingsOut:
    # One transaction persists all four values; a failed commit applies none of
    # them. Keep the legacy individual endpoints serialized with queue updates.
    with _configuration_lock:
        row = session.get(TaskQueueConfig, "default", populate_existing=True)
        image = session.get(ImageProcessingConfig, "default", populate_existing=True)
        if row is None:
            row = TaskQueueConfig(id="default")
            session.add(row)
        if image is None:
            image = ImageProcessingConfig(id="default")
            session.add(image)
        row.download_workers = data.download_workers
        row.sync_workers = data.scan_metadata_workers
        image.conversion_workers = data.conversion_workers
        image.thumbnail_workers = data.thumbnail_workers
        session.commit()
        _apply(row)
        processing.configure_processing(session)
        return get_worker_settings(session)
