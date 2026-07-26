"""Remote chapter index: cache provider feed listings and merge with local downloads.

Matched series (e.g. MangaDex account sync) often have no local Chapter rows until
the user downloads. This module persists the provider feed as ``ProviderChapter``
rows so the series detail chapter list can show availability + download status.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.models import Chapter, ProviderChapter, Series
from src.core.exceptions import BadRequestError, NotFoundError
from src.core.logging import get_logger
from src.core.persistence.base_model import utc_now
from src.downloads.models import DownloadTask
from src.downloads.provider import RemoteChapter, get_provider
from src.integrations.models import Provider as ProviderConfig

logger = get_logger(__name__)

# Refresh the index when empty or older than this (series open / list_chapters).
_INDEX_TTL = timedelta(hours=6)


def _number_sort(number: str | None) -> float | None:
    if not number:
        return None
    try:
        return float(number)
    except ValueError:
        return None


def _parse_published(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def upsert_provider_chapters(
    session: Session,
    series: Series,
    remotes: list[RemoteChapter],
    *,
    provider: str | None = None,
) -> int:
    """Upsert remote feed rows for a series. Returns the number of remotes processed."""
    provider_id = provider or series.provider or "mangadex"
    now = utc_now()
    existing = {
        row.provider_chapter_id: row
        for row in session.scalars(
            select(ProviderChapter).where(
                ProviderChapter.series_id == series.id,
                ProviderChapter.provider == provider_id,
            )
        )
    }
    seen: set[str] = set()
    for remote in remotes:
        seen.add(remote.provider_chapter_id)
        row = existing.get(remote.provider_chapter_id)
        if row is None:
            row = ProviderChapter(
                series_id=series.id,
                provider=provider_id,
                provider_chapter_id=remote.provider_chapter_id,
            )
            session.add(row)
            existing[remote.provider_chapter_id] = row
        row.volume = remote.volume
        row.number = remote.number
        row.number_sort = _number_sort(remote.number)
        row.title = remote.title
        row.language = remote.language
        row.group_name = remote.group_name
        row.published_at = _parse_published(remote.published_at)
        row.last_seen_at = now

    # Drop entries no longer in the feed (removed / language filter changed).
    for pid, row in list(existing.items()):
        if pid not in seen:
            session.delete(row)

    local_numbers = set(
        session.scalars(select(Chapter.number).where(Chapter.series_id == series.id))
    )
    series.available_chapters = sum(1 for r in remotes if r.number not in local_numbers)
    series.chapter_index_at = now
    session.flush()
    return len(remotes)


def refresh_series_chapter_index(session: Session, series_id: str) -> int:
    """Fetch the provider feed for a matched series and upsert the index. Returns count."""
    series = session.get(Series, series_id)
    if series is None:
        raise NotFoundError(f"series {series_id!r} not found")
    if not series.provider or not series.provider_series_id:
        raise BadRequestError("series is not matched to a provider")
    provider = get_provider(series.provider)
    if provider is None:
        raise BadRequestError(f"provider {series.provider!r} is not available")
    config = session.get(ProviderConfig, series.provider)
    language = config.language if config else "en"
    remotes = provider.list_chapters(series.provider_series_id, language=language)
    return upsert_provider_chapters(session, series, remotes, provider=series.provider)


def index_is_stale(session: Session, series_id: str) -> bool:
    """True when the series is matched and the chapter index is missing or past TTL."""
    series = session.get(Series, series_id)
    if series is None or not series.provider or not series.provider_series_id:
        return False
    latest = series.chapter_index_at
    if latest is None:
        return True
    if latest.tzinfo is None:
        latest = latest.replace(tzinfo=UTC)
    return datetime.now(UTC) - latest > _INDEX_TTL


def ensure_chapter_index(session: Session, series_id: str) -> None:
    """Refresh the remote chapter index when stale or missing (best-effort)."""
    series = session.get(Series, series_id)
    if series is None or not series.provider or not series.provider_series_id:
        return
    if not index_is_stale(session, series_id):
        return
    try:
        _ = refresh_series_chapter_index(session, series_id)
        session.commit()
    except Exception as exc:  # noqa: BLE001 - listing must still return local chapters
        session.rollback()
        logger.warning("chapter_index_refresh_failed", series_id=series_id, error=str(exc))


def download_status_map(session: Session, series_id: str) -> dict[str, str]:
    """Map provider_chapter_id → download task status for live queue rows."""
    statuses: dict[str, str] = {}
    for task in session.scalars(
        select(DownloadTask).where(
            DownloadTask.series_id == series_id,
            DownloadTask.status.in_(("queued", "downloading", "paused", "failed")),
        )
    ):
        remote = task.remote_json or {}
        pid = remote.get("provider_chapter_id")
        if isinstance(pid, str) and pid:
            statuses[pid] = task.status
    return statuses


def local_by_provider_id(session: Session, series_id: str) -> dict[str, Chapter]:
    """Local chapters keyed by provider_chapter_id (when set)."""
    out: dict[str, Chapter] = {}
    for chapter in session.scalars(select(Chapter).where(Chapter.series_id == series_id)):
        if chapter.provider_chapter_id:
            out[chapter.provider_chapter_id] = chapter
    return out


def local_by_number_lang(session: Session, series_id: str) -> dict[tuple[str, str], Chapter]:
    """Fallback match for scanned chapters without provider ids."""
    out: dict[tuple[str, str], Chapter] = {}
    for chapter in session.scalars(select(Chapter).where(Chapter.series_id == series_id)):
        if chapter.number is not None:
            out[(chapter.number, chapter.language)] = chapter
    return out
