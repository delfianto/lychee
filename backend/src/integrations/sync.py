"""Provider sync: check every matched series for new remote chapters.

Runs on the background queue: for each series linked to a provider, it diffs the
provider's chapter list against the local chapters and records the count of new
ones on ``Series.available_chapters`` (summed into the sync-state singleton that
backs the Settings → Sync card).
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.models import Chapter, Series
from src.core.logging import get_logger
from src.downloads.provider import get_provider
from src.integrations.models import Provider, SyncState
from src.integrations.schema import SyncOut
from src.integrations.seed import SYNC_STATE_ID
from src.tasks.queue import Work, queue
from src.tasks.schema import TaskOut

logger = get_logger(__name__)
_MANGADEX = "mangadex"


def _sync_state(session: Session) -> SyncState:
    state = session.get(SyncState, SYNC_STATE_ID)
    if state is None:
        state = SyncState(id=SYNC_STATE_ID)
        session.add(state)
        session.flush()
    return state


def _sync_out(state: SyncState) -> SyncOut:
    return SyncOut(
        last_sync=state.last_sync_at,
        auto_every_minutes=state.auto_every_minutes,
        new_chapters=state.new_chapters,
        syncing=state.syncing,
    )


def get_sync(session: Session) -> SyncOut:
    return _sync_out(_sync_state(session))


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
        total_new = 0
        for index, series in enumerate(matched, start=1):
            provider = get_provider(series.provider or "")
            if provider is not None:
                try:
                    remote = provider.list_chapters(series.provider_series_id or "", language=language)
                    local = set(
                        session.scalars(select(Chapter.number).where(Chapter.series_id == series.id))
                    )
                    series.available_chapters = sum(1 for r in remote if r.number not in local)
                    total_new += series.available_chapters
                except Exception as exc:  # noqa: BLE001 - per-series best-effort
                    logger.warning("sync_series_failed", series=series.title, error=str(exc))
            on_progress(round(index / len(matched) * 100) if matched else 100, series.title)
        state = _sync_state(session)
        state.new_chapters = total_new
        state.last_sync_at = datetime.now(UTC)
        state.syncing = False
        return {"newChapters": total_new}

    return work


def run_sync(session: Session) -> TaskOut:
    """Check every matched series for new remote chapters on the background queue."""
    task = queue.submit("sync", "Checking for new chapters", _sync_work())
    return TaskOut.model_validate(task)
