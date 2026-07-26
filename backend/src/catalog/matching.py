"""Link local series to a metadata provider and keep their metadata fresh.

Covers searching for candidates, setting/clearing a match manually, auto-matching
a freshly scanned library (confident exact-title only), and re-fetching metadata
on the background queue. Actual field mapping lives in ``catalog.metadata``.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.media import materialize_series_cover
from src.catalog.metadata import apply_metadata
from src.catalog.models import Series
from src.catalog.schema import MangaMatchOut
from src.core.config import settings
from src.core.exceptions import BadRequestError, NotFoundError
from src.core.logging import get_logger
from src.downloads.provider import MetadataProvider, get_metadata_provider
from src.integrations.models import Provider as ProviderConfig
from src.media.thumbnails import ThumbnailStore
from src.tasks.queue import Work, queue
from src.tasks.schema import TaskOut

logger = get_logger(__name__)
_DEFAULT_PROVIDER = "mangadex"


def _thumb_store() -> ThumbnailStore:
    return ThumbnailStore(Path(settings.storage_path) / "thumbnails")


def _refresh_work(series_id: str, provider_id: str, language: str, fetch_covers: bool) -> Work:
    def work(session: Session, on_progress: Callable[[int, str], None]) -> dict[str, str]:
        series = session.get(Series, series_id)
        if series is None or not series.provider_series_id:  # defensive (validated at enqueue)
            raise NotFoundError(f"series {series_id!r} is no longer matched")
        provider = get_metadata_provider(provider_id)
        if provider is None:
            raise BadRequestError(f"provider {provider_id!r} has no metadata support")
        on_progress(20, series.title)
        meta = provider.get_metadata(series.provider_series_id, language=language)
        on_progress(70, "Applying metadata")
        apply_metadata(session, series, meta, fetch_covers=fetch_covers)
        if fetch_covers:
            on_progress(85, "Warming cover")
            _ = materialize_series_cover(session, _thumb_store(), series_id)
        # Pull the remote chapter index so series detail has chapters without a full download.
        try:
            from src.catalog.remote_chapters import refresh_series_chapter_index

            on_progress(95, "Indexing chapters")
            _ = refresh_series_chapter_index(session, series_id)
        except Exception as exc:  # noqa: BLE001 - chapter index is best-effort on match/refresh
            logger.warning("chapter_index_on_refresh_failed", series_id=series_id, error=str(exc))
        return {"title": series.title}

    return work


def refresh_series(session: Session, series_id: str) -> TaskOut:
    """Validate the series is matched, then re-fetch its provider metadata on the queue."""
    series = session.get(Series, series_id)
    if series is None:
        raise NotFoundError(f"series {series_id!r} not found")
    if not series.provider or not series.provider_series_id:
        raise BadRequestError("series is not matched to a provider")
    config = session.get(ProviderConfig, series.provider)
    language = config.language if config else "en"
    fetch_covers = config.fetch_covers if config else True
    work = _refresh_work(series.id, series.provider, language, fetch_covers)
    return queue.submit_task("metadata", f"Refreshing {series.title}", work)


def _normalize_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def match_candidates(
    session: Session, series_id: str, *, q: str | None = None, limit: int = 5
) -> list[MangaMatchOut]:
    """Provider search hits for matching this series (defaults to searching its title)."""
    series = session.get(Series, series_id)
    if series is None:
        raise NotFoundError(f"series {series_id!r} not found")
    provider = get_metadata_provider(series.provider or _DEFAULT_PROVIDER)
    if provider is None:
        raise BadRequestError("no metadata provider available")
    query = (q or series.title).strip()
    if not query:
        return []
    return [
        MangaMatchOut(
            provider_series_id=m.provider_series_id,
            title=m.title,
            year=m.year,
            status=m.status,
            cover_url=m.cover_url,
        )
        for m in provider.search(query, limit=limit)
    ]


def set_match(
    session: Session, series_id: str, *, provider_id: str, provider_series_id: str
) -> TaskOut:
    """Link a series to a provider entry, then fetch its metadata on the queue."""
    series = session.get(Series, series_id)
    if series is None:
        raise NotFoundError(f"series {series_id!r} not found")
    if get_metadata_provider(provider_id) is None:
        raise BadRequestError(f"provider {provider_id!r} is not available")
    series.provider = provider_id
    series.provider_series_id = provider_series_id
    session.commit()
    return refresh_series(session, series_id)


def unlink_match(session: Session, series_id: str) -> None:
    series = session.get(Series, series_id)
    if series is None:
        raise NotFoundError(f"series {series_id!r} not found")
    series.provider = None
    series.provider_series_id = None
    session.commit()


def _auto_match_one(
    session: Session,
    series: Series,
    provider: MetadataProvider,
    *,
    language: str,
    fetch_covers: bool,
) -> bool:
    target = _normalize_title(series.title)
    match = next(
        (c for c in provider.search(series.title, limit=5) if _normalize_title(c.title) == target),
        None,
    )
    if match is None:
        return False  # only adopt a confident (exact-title) match; else leave for manual
    series.provider = provider.id
    series.provider_series_id = match.provider_series_id
    meta = provider.get_metadata(match.provider_series_id, language=language)
    apply_metadata(session, series, meta, fetch_covers=fetch_covers)
    if fetch_covers:
        _ = materialize_series_cover(session, _thumb_store(), series.id)
    return True


def auto_match_library(session: Session, library_id: str) -> int:
    """Best-guess match + enrich every unmatched series in a library (best-effort)."""
    config = session.get(ProviderConfig, _DEFAULT_PROVIDER)
    if config is None or not config.enabled or not config.auto_match:
        return 0
    provider = get_metadata_provider(_DEFAULT_PROVIDER)
    if provider is None:
        return 0
    unmatched = list(
        session.scalars(
            select(Series).where(Series.library_id == library_id, Series.provider.is_(None))
        )
    )
    matched = 0
    for series in unmatched:
        try:
            if _auto_match_one(
                session,
                series,
                provider,
                language=config.language,
                fetch_covers=config.fetch_covers,
            ):
                matched += 1
        except Exception as exc:  # noqa: BLE001 - best-effort; one failure shouldn't abort the scan
            logger.warning("auto_match_failed", series=series.title, error=str(exc))
    return matched
