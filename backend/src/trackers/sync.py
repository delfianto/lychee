"""Outbound reading-progress push to connected trackers.

When a chapter is completed, ``enqueue_push`` schedules a background ``tracker``
task (only if a tracker is actually connected, so idle reads cost nothing). The
task resolves each connected tracker's media id from ``Series.external_ids`` and
pushes read count + status best-effort — a tracker being down never fails a read.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.catalog.models import Series
from src.core.crypto import decrypt
from src.core.logging import get_logger
from src.integrations.models import Tracker
from src.progress.models import ReadingProgress
from src.tasks.queue import Work, queue
from src.trackers.base import get_tracker

logger = get_logger(__name__)
_PUSHABLE = {"reading", "completed", "on_hold", "dropped", "plan_to_read", "re_reading"}


def _connected(session: Session) -> bool:
    """Is any outbound sink connected — a sync-on-read tracker, or the MangaDex account?"""
    trackers = session.scalar(
        select(func.count())
        .select_from(Tracker)
        .where(Tracker.connected.is_(True), Tracker.sync_on_read.is_(True))
    )
    if trackers:
        return True
    from src.providers import mangadex_account  # lazy import to avoid an import cycle

    return mangadex_account.is_connected(session)


def push_series_progress(session: Session, series_id: str) -> int:
    """Push this series' read count + status to every connected tracker. Returns #pushed."""
    series = session.get(Series, series_id)
    if series is None:
        return 0
    external = series.external_ids_json or {}
    if not external:
        return 0
    read_count = (
        session.scalar(
            select(func.count())
            .select_from(ReadingProgress)
            .where(ReadingProgress.series_id == series_id, ReadingProgress.completed.is_(True))
        )
        or 0
    )
    total = series.total_chapters or 0
    if total and read_count >= total:
        status = "completed"
    elif series.library_status in _PUSHABLE:
        status = series.library_status
    else:
        status = "reading"

    pushed = 0
    for tracker in session.scalars(
        select(Tracker).where(Tracker.connected.is_(True), Tracker.sync_on_read.is_(True))
    ):
        impl = get_tracker(tracker.id)
        media_id = external.get(impl.external_id_key) if impl else None
        if impl is None or not tracker.access_token_enc or not media_id:
            continue
        try:
            impl.push(
                access_token=decrypt(tracker.access_token_enc),
                media_id=media_id,
                status=status,
                progress=read_count,
            )
            pushed += 1
        except Exception as exc:  # noqa: BLE001 - best-effort; a tracker error can't fail a read
            logger.warning("tracker_push_failed", tracker=tracker.id, series=series.title, error=str(exc))
    return pushed


def _push_work(series_id: str) -> Work:
    def work(session: Session, _on_progress: Callable[[int, str], None]) -> dict[str, int]:
        from src.providers import mangadex_account  # lazy import to avoid an import cycle

        pushed = push_series_progress(session, series_id)  # AniList / MyAnimeList / MangaUpdates
        _ = mangadex_account.push_series(session, series_id)  # MangaDex (two-way)
        return {"pushed": pushed}

    return work


def enqueue_push(session: Session, series_id: str) -> None:
    """Schedule an outbound push (no-op unless a tracker is connected)."""
    if _connected(session):
        _ = queue.submit("tracker", "Syncing reading progress", _push_work(series_id))
