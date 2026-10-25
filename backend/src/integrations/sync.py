"""Provider and library sync jobs: progress log, pause/cancel controls, and worker concurrency.

Tracks background sync/scan/account-pull jobs with detailed per-item progress
(what file is being indexed or which manga is being pulled from where, plus any
error reason), supports cooperative pause/resume/cancel, and runs provider chapter
checks across up to ``queue.sync_workers`` (1–10) parallel workers.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.models import Series
from src.catalog.remote_chapters import upsert_provider_chapters
from src.core.exceptions import BadRequestError, NotFoundError
from src.core.logging import get_logger
from src.core.persistence.base_model import gen_id
from src.downloads.provider import RemoteChapter, get_provider
from src.integrations.models import Provider, SyncState
from src.integrations.schema import SyncConfigUpdate, SyncControlRequest, SyncJobOut, SyncOut
from src.integrations.seed import SYNC_STATE_ID
from src.tasks.concurrency import parallel_map
from src.tasks.config import save_queue_workers
from src.tasks.context import OperationCancelled, checkpoint, current_operation, report_phase
from src.tasks.events import broker
from src.tasks.queue import MAX_WORKERS, Work, queue
from src.tasks.schema import TaskOut
from src.tasks.tracker import tracker

logger = get_logger(__name__)
_MANGADEX = "mangadex"
_VALID_ACTIONS = frozenset(
    {"pause", "pause-all", "resume", "resume-all", "cancel", "cancel-all", "clear-completed"}
)
_ACTIVE_STATUSES = frozenset({"queued", "running", "paused", "cancelling"})
_FINISHED_STATUSES = frozenset({"done", "failed", "cancelled"})


SyncCancelled = OperationCancelled


@dataclass
class SyncJob:
    id: str
    kind: str
    title: str
    source: str
    status: str = "queued"
    progress: int = 0
    detail: str | None = None
    error: str | None = None
    paused_requested: bool = False
    cancel_requested: bool = False
    task_id: str | None = None
    operation_finished: bool = False


class SyncJobManager:
    """Thread-safe registry of active and recent sync/scan jobs with pause & cancel."""

    def __init__(self, *, max_keep: int = 200) -> None:
        self._jobs: dict[str, SyncJob] = {}
        self._order: list[str] = []
        self._paused: bool = False
        self._cond = threading.Condition()
        self._max_keep = max_keep

    @property
    def auto_clear_completed(self) -> bool:
        with self._cond:
            return queue.auto_clear_syncs

    def _clear_successful(self) -> None:
        if queue.auto_clear_syncs:
            self._order = [
                jid
                for jid in self._order
                if self._jobs[jid].status != "done"
                or (
                    self._jobs[jid].kind in {"scan", "import"}
                    and self._jobs[jid].task_id
                    and not self._jobs[jid].operation_finished
                )
            ]
            self._jobs = {jid: self._jobs[jid] for jid in self._order}
        # The history cap must not evict queued/running folder or chapter checks.
        # Otherwise large syncs silently undercount and lose cancellation controls.
        finished = [jid for jid in self._order if self._jobs[jid].status in _FINISHED_STATUSES]
        expired = set(finished[: max(0, len(finished) - self._max_keep)])
        if expired:
            self._order = [jid for jid in self._order if jid not in expired]
            for jid in expired:
                del self._jobs[jid]

    @property
    def paused(self) -> bool:
        with self._cond:
            return self._paused

    def reset(self) -> None:
        with self._cond:
            self._jobs.clear()
            self._order.clear()
            self._paused = False
            queue.auto_clear_syncs = False
            self._cond.notify_all()

    def create(
        self,
        *,
        kind: str,
        title: str,
        source: str,
        status: str = "queued",
        progress: int = 0,
        detail: str | None = None,
        error: str | None = None,
    ) -> SyncJob:
        with self._cond:
            initial_status = "paused" if self._paused and status == "queued" else status
            job = SyncJob(
                id=gen_id(),
                kind=kind,
                title=title,
                source=source,
                status=initial_status,
                progress=progress,
                detail=detail,
                error=error,
                paused_requested=self._paused,
            )
            operation = current_operation.get()
            if operation is not None:
                job.task_id = operation.task_id
                if kind in {"scan", "import"}:
                    operation.checks.append(lambda: self.check_state(job.id))
                operation.finalizers.append(lambda status: self.finish_operation(job.id, status))
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._clear_successful()
            broker.publish({"event": "activity.changed"})
            return job

    def finish_operation(self, job_id: str, status: str) -> None:
        with self._cond:
            job = self._jobs.get(job_id)
            if job is not None:
                job.operation_finished = True
            if job is not None and (
                job.status not in {"done", "failed", "cancelled"}
                or (job.kind in {"scan", "import"} and status != "done")
            ):
                job.status = status
                if status == "done":
                    job.progress = 100
                elif status == "cancelled":
                    job.detail = "Cancelled"
            self._clear_successful()
            broker.publish({"event": "activity.changed"})

    def update(
        self,
        job_id: str,
        *,
        status: str | None = None,
        progress: int | None = None,
        detail: str | None = None,
        error: str | None = None,
    ) -> SyncJob | None:
        with self._cond:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            if status is not None:
                job.status = status
            if progress is not None:
                job.progress = max(0, min(100, int(progress)))
            if detail is not None:
                job.detail = detail
            if error is not None:
                job.error = error
            self._clear_successful()
            if status is not None:
                broker.publish({"event": "activity.changed"})
            return job

    def check_state(self, job_id: str) -> None:
        """Block while paused; raise :class:`SyncCancelled` if cancelled."""
        with self._cond:
            job = self._jobs.get(job_id)
            if job is None:
                return
            while (self._paused or job.paused_requested) and not job.cancel_requested:
                if job.task_id:
                    tracker.checkpoint(job.task_id)
                job.status = "paused"
                self._cond.wait(timeout=0.5)
            if job.cancel_requested:
                job.status = "cancelling" if job.task_id else "cancelled"
                job.detail = "Cancelled"
                raise SyncCancelled(f"sync job {job_id} cancelled")
            if job.status in {"queued", "paused"}:
                job.status = "running"

    def control(self, action: str, *, job_id: str | None = None) -> None:
        if action not in _VALID_ACTIONS:
            raise BadRequestError(f"unknown sync action {action!r}")
        with self._cond:
            broker.publish({"event": "activity.changed"})
            if action == "clear-completed":
                keep_ids = [
                    jid
                    for jid in self._order
                    if jid in self._jobs and self._jobs[jid].status not in _FINISHED_STATUSES
                ]
                self._order = keep_ids
                self._jobs = {jid: self._jobs[jid] for jid in keep_ids}
                return

            if job_id is not None:
                job = self._jobs.get(job_id)
                if job is None:
                    raise NotFoundError(f"sync job {job_id!r} not found")
                if action in {"pause", "pause-all"}:
                    if job.status in {"queued", "running"}:
                        job.paused_requested = True
                        job.status = "paused"
                elif action in {"resume", "resume-all"}:
                    job.paused_requested = False
                    if job.status == "paused":
                        job.status = "queued"
                elif action in {"cancel", "cancel-all"}:
                    job.cancel_requested = True
                    if job.task_id and job.kind in {"scan", "import"}:
                        tracker.cancel(job.task_id)
                    job.paused_requested = False
                    if job.status in _ACTIVE_STATUSES:
                        job.status = "cancelling" if job.task_id else "cancelled"
                        job.detail = "Cancelled"
                self._cond.notify_all()
                return

            if action in {"pause", "pause-all"}:
                self._paused = True
                for job in self._jobs.values():
                    if job.status in {"queued", "running"}:
                        job.paused_requested = True
                        job.status = "paused"
            elif action in {"resume", "resume-all"}:
                self._paused = False
                for job in self._jobs.values():
                    job.paused_requested = False
                    if job.status == "paused":
                        job.status = "queued"
            elif action in {"cancel", "cancel-all"}:
                self._paused = False
                for job in self._jobs.values():
                    if job.status in _ACTIVE_STATUSES:
                        job.cancel_requested = True
                        if job.task_id:
                            tracker.cancel(job.task_id)
                        job.paused_requested = False
                        job.status = "cancelling" if job.task_id else "cancelled"
                        job.detail = "Cancelled"
            self._cond.notify_all()

    def list_jobs(self) -> list[SyncJobOut]:
        with self._cond:
            self._clear_successful()
            return [
                SyncJobOut(
                    id=self._jobs[jid].id,
                    kind=self._jobs[jid].kind,
                    title=self._jobs[jid].title,
                    source=self._jobs[jid].source,
                    status=self._jobs[jid].status,
                    progress=self._jobs[jid].progress,
                    detail=self._jobs[jid].detail,
                    error=self._jobs[jid].error,
                    task_id=self._jobs[jid].task_id,
                    phases=next(
                        (
                            task.phases
                            for task in tracker.snapshot()
                            if task.id == self._jobs[jid].task_id
                        ),
                        {},
                    ),
                )
                for jid in reversed(self._order)
                if jid in self._jobs
            ]

    def activity_snapshot(self) -> list[tuple[str | None, str]]:
        """Avoid joining task phases / materializing the settings log just to count."""
        with self._cond:
            return [(job.task_id, job.status) for job in self._jobs.values()]

    def has_active(self) -> bool:
        with self._cond:
            return any(j.status in _ACTIVE_STATUSES for j in self._jobs.values())


sync_jobs = SyncJobManager()


def _sync_state(session: Session) -> SyncState:
    state = session.get(SyncState, SYNC_STATE_ID)
    if state is None:
        state = SyncState(id=SYNC_STATE_ID)
        session.add(state)
        session.flush()
    return state


def _sync_out(state: SyncState) -> SyncOut:
    jobs = sync_jobs.list_jobs()
    active = any(j.status in _ACTIVE_STATUSES for j in jobs)
    return SyncOut(
        last_sync=state.last_sync_at,
        auto_every_minutes=state.auto_every_minutes,
        new_chapters=state.new_chapters,
        syncing=active
        or any(
            task.kind == "sync" and task.status in {"queued", "running", "cancelling"}
            for task in tracker.snapshot()
        ),
        paused=sync_jobs.paused,
        parallel_syncs=queue.sync_workers,
        auto_clear_completed=sync_jobs.auto_clear_completed,
        jobs=jobs,
    )


def get_sync(session: Session) -> SyncOut:
    return _sync_out(_sync_state(session))


def update_sync_config(session: Session, data: SyncConfigUpdate) -> SyncOut:
    save_queue_workers(
        session, "sync", data.parallel_syncs, auto_clear_completed=data.auto_clear_completed
    )
    return get_sync(session)


def control_sync(session: Session, data: SyncControlRequest) -> SyncOut:
    sync_jobs.control(data.action, job_id=data.job_id)
    if data.action in {"cancel", "cancel-all"} and data.job_id is None:
        for task in tracker.snapshot():
            if task.kind in {"scan", "sync", "import", "thumbs", "metadata"}:
                tracker.cancel(task.id)
    if data.action in {"cancel", "cancel-all"} and not sync_jobs.has_active():
        state = _sync_state(session)
        state.syncing = False
        session.commit()
    return get_sync(session)


def _fetch_series_remote_chapters(
    job_id: str,
    title: str,
    provider_id: str,
    provider_series_id: str,
    language: str,
) -> list[RemoteChapter] | Exception:
    try:
        checkpoint()
        sync_jobs.check_state(job_id)
    except SyncCancelled as exc:
        return exc
    provider = get_provider(provider_id)
    if provider is None:
        err = RuntimeError(f"provider {provider_id!r} is not available")
        _ = sync_jobs.update(
            job_id,
            status="failed",
            detail=f"Failed pulling {title} from {provider_id}",
            error=str(err),
        )
        return err
    _ = sync_jobs.update(
        job_id,
        status="running",
        progress=30,
        detail=f"Pulling chapters for {title} from {provider_id}",
    )
    try:
        with queue.io_limit.slot():
            remotes = provider.list_chapters(provider_series_id, language=language)
        checkpoint()
        sync_jobs.check_state(job_id)
        return remotes
    except SyncCancelled as exc:
        return exc
    except Exception as exc:  # noqa: BLE001
        logger.warning("sync_series_failed", series=title, error=str(exc))
        _ = sync_jobs.update(
            job_id,
            status="failed",
            detail=f"Failed pulling {title} from {provider_id}",
            error=str(exc),
        )
        return exc


def _sync_work() -> Work:
    def work(session: Session, on_progress: Callable[[int, str], None]) -> dict[str, int]:
        config = session.get(Provider, _MANGADEX)
        language = config.language if config else "en"
        matched = list(
            session.scalars(
                select(Series).where(
                    Series.provider.is_not(None), Series.provider_series_id.is_not(None)
                )
            )
        )
        state = _sync_state(session)
        state.syncing = True
        session.commit()

        planned: list[tuple[Series, SyncJob, str]] = []
        for series in matched:
            source = (series.provider or _MANGADEX).capitalize()
            if source.lower() == "mangadex":
                source = "MangaDex"
            job = sync_jobs.create(
                kind="sync",
                title=series.title,
                source=source,
                status="queued",
                detail=f"Queued chapter check from {source}",
            )
            planned.append((series, job, source))

        workers = MAX_WORKERS
        total_new = 0
        completed = 0
        total = len(planned) or 1

        report_phase("chapters", 0, len(planned), "Checking chapter availability")
        requests = [
            (
                series.id,
                job.id,
                series.title,
                series.provider or _MANGADEX,
                series.provider_series_id or "",
                source,
            )
            for series, job, source in planned
        ]
        by_id = {series.id: series for series, _, _ in planned}

        def fetch(item: tuple[str, str, str, str, str, str]):
            series_id, job_id, title, provider_id, provider_series_id, source = item
            return (
                series_id,
                job_id,
                source,
                _fetch_series_remote_chapters(
                    job_id, title, provider_id, provider_series_id, language
                ),
            )

        for series_id, job_id, source, outcome in parallel_map(
            fetch, requests, workers=workers, limit=queue.io_limit
        ):
            series = by_id[series_id]
            job = next(job for _, job, _ in planned if job.id == job_id)
            completed += 1
            report_phase("chapters", completed, total, series.title)
            if isinstance(outcome, SyncCancelled):
                _ = sync_jobs.update(job.id, status="cancelled", detail="Cancelled")
                on_progress(round(completed / total * 100), f"Cancelled {series.title}")
                continue
            if isinstance(outcome, Exception):
                on_progress(round(completed / total * 100), f"Error: {series.title}")
                continue
            try:
                sync_jobs.check_state(job.id)
                _ = upsert_provider_chapters(
                    session, series, outcome, provider=series.provider or _MANGADEX
                )
                session.commit()
                total_new += series.available_chapters
                _ = sync_jobs.update(
                    job.id,
                    status="done",
                    progress=100,
                    detail=f"Pulled from {source} · {series.available_chapters} new chapter(s)",
                )
            except SyncCancelled:
                session.rollback()
            except Exception as exc:  # noqa: BLE001
                session.rollback()
                logger.warning("sync_series_upsert_failed", series=series.title, error=str(exc))
                _ = sync_jobs.update(
                    job.id,
                    status="failed",
                    detail=f"Failed indexing chapters for {series.title} from {source}",
                    error=str(exc),
                )
            on_progress(round(completed / total * 100), series.title)

        state = _sync_state(session)
        state.new_chapters = total_new
        state.last_sync_at = datetime.now(UTC)
        state.syncing = False
        session.commit()
        return {"newChapters": total_new}

    return work


def run_sync(session: Session) -> TaskOut:
    """Check every matched series for new remote chapters on the background queue."""
    return queue.submit_task("sync", "Checking for new chapters", _sync_work())
