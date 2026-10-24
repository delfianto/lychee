"""Downloads services (queue over DownloadTask; synchronous pipeline in v1)."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from threading import Lock

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from src.catalog import repository as catalog_repo
from src.catalog.models import Series
from src.catalog.service import to_series_out
from src.core.exceptions import BadRequestError, NotFoundError
from src.downloads.cancel import clear_cancel, request_cancel, request_cancel_many
from src.downloads.downloader import plan_downloads, resolve_manga_library, run_download_queue
from src.downloads.models import DownloadTask
from src.downloads.provider import get_provider
from src.downloads.schema import DownloadConfigOut, DownloadConfigUpdate, DownloadTaskOut
from src.integrations.models import Provider as ProviderConfig
from src.tasks.concurrency import parallel_map
from src.tasks.config import save_queue_workers
from src.tasks.queue import MAX_WORKERS, Work, queue
from src.tasks.schema import TaskOut

_BULK_ACTIONS = frozenset({"pause-all", "cancel-all", "resume-all"})


def get_download_config() -> DownloadConfigOut:
    return DownloadConfigOut(parallel_downloads=queue.download_workers)


def update_download_config(session: Session, data: DownloadConfigUpdate) -> DownloadConfigOut:
    save_queue_workers(session, "download", data.parallel_downloads)
    return get_download_config()


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
                phase=row.phase,
                phases=row.phases_json or {},
                detail=row.detail,
                size_bytes=row.size_bytes,
            )
        )
    return out


def list_downloads(session: Session) -> list[DownloadTaskOut]:
    rows = list(session.scalars(select(DownloadTask).order_by(DownloadTask.created_at.desc())))
    return _tasks_out(session, rows)


def _drain_parallel(
    session: Session, series_id: str, storage_root: Path, on_progress: Callable[[int, str], None]
) -> int:
    """All chapter workers belong to one operation and are joined before it finishes."""
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    values = dict(
        session.execute(
            select(DownloadTask.id, DownloadTask.progress).where(
                DownloadTask.series_id == series_id,
                DownloadTask.status.in_(("queued", "downloading")),
            )
        ).all()
    )
    session.commit()
    if not values:
        return 0
    progress_lock = Lock()

    def progress(task_id: str, pct: int, detail: str) -> None:
        # Progress must never need another connection while its owner is doing
        # chapter work. The starting snapshot plus live callbacks replaces a
        # SELECT avg(...) on every page/phase update.
        with progress_lock:
            values[task_id] = pct
            average = sum(values.values()) / max(1, len(values))
        on_progress(min(99, round(average)), detail)

    def drain(_: int) -> int:
        # A Session object itself is cheap; its first database query happens only
        # after run_download_queue acquires global chapter capacity.
        with factory() as worker_session:
            return run_download_queue(worker_session, series_id, storage_root, on_progress=progress)

    workers = min(MAX_WORKERS, len(values))
    return sum(parallel_map(drain, range(workers), workers=workers, limit=queue.chapter_limit))


def _download_work(
    series_id: str,
    storage_root: Path,
    *,
    provider_chapter_ids: list[str] | None = None,
) -> Work:
    """Task that plans a series' pending chapters into the queue, then drains it."""

    def work(session: Session, on_progress: Callable[[int, str], None]) -> dict[str, int]:
        series = session.get(Series, series_id)
        if series is None or not series.provider:
            raise BadRequestError("series is not linked to a provider")
        provider = get_provider(series.provider)
        if provider is None:
            raise BadRequestError(f"provider {series.provider!r} is not available")
        config = session.get(ProviderConfig, series.provider)
        language = config.language if config else "en"
        session.commit()  # do not retain a connection during provider HTTP requests
        _ = plan_downloads(
            session,
            series,
            provider,
            language=language,
            provider_chapter_ids=provider_chapter_ids,
        )
        return {"downloaded": _drain_parallel(session, series_id, storage_root, on_progress)}

    return work


def _resume_work(series_id: str, storage_root: Path) -> Work:
    """Task that drains a series' already-queued rows (from resume/retry) without planning."""

    def work(session: Session, on_progress: Callable[[int, str], None]) -> dict[str, int]:
        return {"downloaded": _drain_parallel(session, series_id, storage_root, on_progress)}

    return work


def create_downloads(
    session: Session,
    series_id: str,
    storage_root: Path,
    *,
    provider_chapter_ids: list[str] | None = None,
) -> TaskOut:
    """Validate the series + provider + manga library, then run the download on the queue."""
    series = session.get(Series, series_id)
    if series is None:
        raise NotFoundError(f"series {series_id!r} not found")
    if not series.provider:
        raise BadRequestError("series is not linked to a provider")
    provider = get_provider(series.provider)
    if provider is None:
        raise BadRequestError(f"provider {series.provider!r} is not available")
    # Fail fast before enqueueing — no manga library means nowhere human-readable to write.
    _ = resolve_manga_library(session)
    label = f"Downloading {series.title}"
    if provider_chapter_ids and len(provider_chapter_ids) == 1:
        label = f"Downloading chapter for {series.title}"
    clear_cancel(series_id)
    return queue.submit_task(
        "download",
        label,
        _download_work(series_id, storage_root, provider_chapter_ids=provider_chapter_ids),
    )


def bulk_action(session: Session, action: str, storage_root: Path) -> list[DownloadTaskOut]:
    """Apply a queue-wide action: pause-all | cancel-all | resume-all."""
    if action not in _BULK_ACTIONS:
        raise BadRequestError(f"unknown download action {action!r}")

    if action == "pause-all":
        for row in session.scalars(select(DownloadTask).where(DownloadTask.status == "queued")):
            row.status = "paused"
        session.commit()
        return list_downloads(session)

    if action == "cancel-all":
        # Stop in-flight drains cooperatively; remove everything else from the queue.
        active_series = list(
            session.scalars(
                select(DownloadTask.series_id)
                .where(
                    DownloadTask.status.in_(("queued", "downloading", "paused")),
                    DownloadTask.series_id.is_not(None),
                )
                .distinct()
            )
        )
        request_cancel_many([sid for sid in active_series if sid])
        # Drop non-running rows immediately; downloading rows finish/fail via cancel flag.
        _ = session.execute(
            delete(DownloadTask).where(DownloadTask.status.in_(("queued", "paused", "failed")))
        )
        for row in session.scalars(
            select(DownloadTask).where(DownloadTask.status == "downloading")
        ):
            row.error = "cancelled"
        session.commit()
        return list_downloads(session)

    # resume-all
    series_ids: set[str] = set()
    for row in session.scalars(select(DownloadTask).where(DownloadTask.status == "paused")):
        row.status = "queued"
        if row.series_id:
            series_ids.add(row.series_id)
    session.commit()
    for sid in series_ids:
        clear_cancel(sid)
        series = session.get(Series, sid)
        label = f"Resuming {series.title}" if series else f"Resuming {sid}"
        _ = queue.submit("download", label, _resume_work(sid, storage_root))
    return list_downloads(session)


def pause_download(session: Session, task_id: str) -> list[DownloadTaskOut]:
    """Hold a queued chapter so the runner skips it. Only a queued row can be paused —
    the in-flight chapter can't be interrupted mid-page."""
    task = session.get(DownloadTask, task_id)
    if task is None:
        raise NotFoundError(f"download {task_id!r} not found")
    if task.status == "paused":
        return list_downloads(session)  # idempotent
    if task.status != "queued":
        raise BadRequestError("only a queued download can be paused")
    task.status = "paused"
    session.commit()
    return list_downloads(session)


def resume_download(session: Session, task_id: str, storage_root: Path) -> list[DownloadTaskOut]:
    """Re-queue a paused chapter and kick a runner to drain it."""
    task = session.get(DownloadTask, task_id)
    if task is None:
        raise NotFoundError(f"download {task_id!r} not found")
    if task.status != "paused":
        raise BadRequestError("download is not paused")
    if task.series_id is None:
        raise BadRequestError("download has no series to resume")
    clear_cancel(task.series_id)
    task.status = "queued"
    session.commit()
    _ = queue.submit(
        "download", f"Resuming {task.chapter_label}", _resume_work(task.series_id, storage_root)
    )
    return list_downloads(session)


def retry_download(session: Session, task_id: str, storage_root: Path) -> TaskOut:
    """Re-queue a failed chapter (reusing its row + stashed remote) and kick a runner.
    Legacy rows with no stashed chapter fall back to re-planning the whole series."""
    task = session.get(DownloadTask, task_id)
    if task is None:
        raise NotFoundError(f"download {task_id!r} not found")
    if task.series_id is None:
        raise BadRequestError("download has no series to retry")
    if task.remote_json is None:
        return create_downloads(session, task.series_id, storage_root)
    clear_cancel(task.series_id)
    task.status = "queued"
    task.error = None
    task.progress = 0
    session.commit()
    return queue.submit_task(
        "download", f"Retrying {task.chapter_label}", _resume_work(task.series_id, storage_root)
    )


def delete_download(session: Session, task_id: str) -> None:
    task = session.get(DownloadTask, task_id)
    if task is None:
        raise NotFoundError(f"download {task_id!r} not found")
    if task.status == "downloading" and task.series_id:
        # Ask the runner to stop; drop the row so it disappears from the UI.
        request_cancel(task.series_id)
    session.delete(task)
    session.commit()


def clear_completed(session: Session) -> None:
    _ = session.execute(delete(DownloadTask).where(DownloadTask.status == "done"))
    session.commit()
