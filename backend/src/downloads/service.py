"""Downloads services (queue over DownloadTask; synchronous pipeline in v1)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.catalog import repository as catalog_repo
from src.catalog.models import Series
from src.catalog.service import to_series_out
from src.core.exceptions import BadRequestError, NotFoundError
from src.downloads.downloader import download_series
from src.downloads.models import DownloadTask
from src.downloads.provider import get_provider
from src.downloads.schema import DownloadTaskOut
from src.tasks.queue import Work, queue
from src.tasks.schema import TaskOut


def _tasks_out(session: Session, rows: list[DownloadTask]) -> list[DownloadTaskOut]:
    series_map = catalog_repo.get_series_rows(session, [r.series_id for r in rows if r.series_id])
    out: list[DownloadTaskOut] = []
    for row in rows:
        srow = series_map.get(row.series_id) if row.series_id else None
        if srow is None:
            continue
        out.append(
            DownloadTaskOut(
                id=row.id,
                series=to_series_out(srow),
                chapter=row.chapter_label,
                status=row.status,
                progress=row.progress,
                size_bytes=row.size_bytes,
            )
        )
    return out


def list_downloads(session: Session) -> list[DownloadTaskOut]:
    rows = list(session.scalars(select(DownloadTask).order_by(DownloadTask.created_at.desc())))
    return _tasks_out(session, rows)


def _download_work(series_id: str, storage_root: Path) -> Work:
    def work(session: Session, on_progress: Callable[[int, str], None]) -> dict[str, int]:
        series = session.get(Series, series_id)
        if series is None or not series.provider:
            raise BadRequestError("series is not linked to a provider")
        provider = get_provider(series.provider)
        if provider is None:
            raise BadRequestError(f"provider {series.provider!r} is not available")
        tasks = download_series(session, series, provider, storage_root, on_progress=on_progress)
        return {"downloaded": len(tasks)}

    return work


def create_downloads(session: Session, series_id: str, storage_root: Path) -> TaskOut:
    """Validate the series + provider (here), then run the download on the task queue."""
    series = session.get(Series, series_id)
    if series is None:
        raise NotFoundError(f"series {series_id!r} not found")
    if not series.provider:
        raise BadRequestError("series is not linked to a provider")
    provider = get_provider(series.provider)
    if provider is None:
        raise BadRequestError(f"provider {series.provider!r} is not available")
    task = queue.submit("download", f"Downloading {series.title}", _download_work(series_id, storage_root))
    return TaskOut.model_validate(task)


def retry_download(session: Session, task_id: str, storage_root: Path) -> TaskOut:
    task = session.get(DownloadTask, task_id)
    if task is None:
        raise NotFoundError(f"download {task_id!r} not found")
    if task.series_id is None:
        raise BadRequestError("download has no series to retry")
    return create_downloads(session, task.series_id, storage_root)


def delete_download(session: Session, task_id: str) -> None:
    task = session.get(DownloadTask, task_id)
    if task is None:
        raise NotFoundError(f"download {task_id!r} not found")
    session.delete(task)
    session.commit()


def clear_completed(session: Session) -> None:
    _ = session.execute(delete(DownloadTask).where(DownloadTask.status == "done"))
    session.commit()
