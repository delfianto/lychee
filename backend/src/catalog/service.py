"""Catalog services — parse query params and assemble API responses."""

from __future__ import annotations

import re
from collections.abc import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog import repository as repo
from src.catalog.metadata import apply_metadata
from src.catalog.models import Series
from src.catalog.repository import ChapterRow, SeriesFilters, SeriesRow, UpdateRow
from src.catalog.schema import (
    ChapterDetailOut,
    ChapterOut,
    DashboardOut,
    DashboardStats,
    LibrarySummaryOut,
    MangaMatchOut,
    RecentUpdateOut,
    SeriesArtOut,
    SeriesOut,
    SeriesUpdate,
    TagOut,
    VolumeGroupOut,
)
from src.core.exceptions import BadRequestError, NotFoundError
from src.core.logging import get_logger
from src.core.schema import Page
from src.downloads.provider import MetadataProvider, get_metadata_provider
from src.integrations.models import Provider as ProviderConfig
from src.tasks.queue import Work, queue
from src.tasks.schema import TaskOut

logger = get_logger(__name__)
_DEFAULT_PROVIDER = "mangadex"

_LIBRARY_STATUSES = {
    "none",
    "reading",
    "on_hold",
    "dropped",
    "plan_to_read",
    "completed",
    "re_reading",
}

_MAX_LIMIT = 100


def cover_url(series_id: str, cover_source: str | None = None) -> str:
    # A remote provider cover (MangaDex) is hotlinked directly; local content is
    # served (and thumbnailed) by our own cover endpoint.
    if cover_source and cover_source.startswith("http"):
        return cover_source
    return f"/api/series/{series_id}/cover"


def _csv(value: str | None) -> list[str]:
    return [part for part in value.split(",") if part] if value else []


def _parse_tags(tags: str | None) -> tuple[list[str], list[str]]:
    """Split a tag csv into (include, exclude); a leading ``-`` marks exclusion."""
    include: list[str] = []
    exclude: list[str] = []
    for raw in _csv(tags):
        (exclude if raw.startswith("-") else include).append(raw.removeprefix("-"))
    return include, exclude


def to_series_out(row: SeriesRow) -> SeriesOut:
    s = row.series
    return SeriesOut(
        id=s.id,
        title=s.title,
        cover_url=cover_url(s.id, s.cover_source),
        authors=[c.name for c in s.credits if c.role == "author"],
        artists=[c.name for c in s.credits if c.role == "artist"],
        status=s.status,
        content_rating=s.content_rating,
        demographic=s.demographic,
        tags=[TagOut(id=t.id, name=t.name, group=t.group) for t in s.tags],
        chapter_count=row.chapter_count,
        unread_count=row.unread_count,
        year=s.year,
        description=s.description,
        last_read_chapter=row.last_read,
        total_chapters=s.total_chapters,
        origin_country=s.origin_country,
        rating=s.rating,
        user_rating=s.user_rating,
        favorite=s.favorite,
        kind=s.kind,
        image_count=s.image_count,
        source=s.source,
        characters=s.characters_json,
        library_status=s.library_status,
        provider=s.provider,
        available_chapters=s.available_chapters,
    )


def build_series_filters(
    *,
    kind: str | None = None,
    shelf: str | None = None,
    favorite: bool | None = None,
    q: str | None = None,
    tags: str | None = None,
    tag_mode: str = "and",
    ratings: str | None = None,
    demographics: str | None = None,
    pub_status: str | None = None,
    read_state: str | None = None,
    artist: str | None = None,
    source: str | None = None,
    sort: str = "recentlyAdded",
) -> SeriesFilters:
    include, exclude = _parse_tags(tags)
    return SeriesFilters(
        kind=kind,
        shelf=shelf,
        favorite=favorite,
        q=q,
        tags_include=include,
        tags_exclude=exclude,
        tag_mode=tag_mode,
        ratings=_csv(ratings),
        demographics=_csv(demographics),
        pub_status=_csv(pub_status),
        read_state=read_state,
        artist=artist,
        source=source,
        sort=sort,
    )


def list_series(
    session: Session, *, filters: SeriesFilters, cursor: str | None, limit: int
) -> Page[SeriesOut]:
    limit = max(1, min(limit, _MAX_LIMIT))
    rows, next_cursor = repo.list_series(session, filters, cursor=cursor, limit=limit)
    return Page[SeriesOut](items=[to_series_out(r) for r in rows], next_cursor=next_cursor)


def get_series(session: Session, series_id: str) -> SeriesOut:
    row = repo.get_series(session, series_id)
    if row is None:
        raise NotFoundError(f"series {series_id!r} not found")
    return to_series_out(row)


def update_series(session: Session, series_id: str, data: SeriesUpdate) -> SeriesOut:
    """Apply detail action-row edits (favorite / shelf status / personal rating)."""
    series = session.get(Series, series_id)
    if series is None:
        raise NotFoundError(f"series {series_id!r} not found")
    fields = data.model_dump(exclude_unset=True)
    if "favorite" in fields:
        series.favorite = bool(fields["favorite"])
    if "library_status" in fields:
        status = fields["library_status"]
        if status not in _LIBRARY_STATUSES:
            raise BadRequestError(f"invalid library status: {status!r}")
        series.library_status = status
    if "rating" in fields:
        series.user_rating = fields["rating"]  # may be None to clear
    session.commit()
    row = repo.get_series(session, series_id)
    assert row is not None  # just updated
    return to_series_out(row)


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
    task = queue.submit("metadata", f"Refreshing {series.title}", work)
    return TaskOut.model_validate(task)


# --- Matching (PART F/M2) -----------------------------------------------------


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
    session: Session, series: Series, provider: MetadataProvider, *, language: str, fetch_covers: bool
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
                session, series, provider, language=config.language, fetch_covers=config.fetch_covers
            ):
                matched += 1
        except Exception as exc:  # noqa: BLE001 - best-effort; one failure shouldn't abort the scan
            logger.warning("auto_match_failed", series=series.title, error=str(exc))
    return matched


def to_chapter_out(row: ChapterRow) -> ChapterOut:
    c = row.chapter
    return ChapterOut(
        id=c.id,
        volume=c.volume,
        number=c.number or "",
        title=c.title,
        group=c.group_name,
        language=c.language,
        uploaded_at=c.source_uploaded_at or c.created_at,
        read=row.read,
        comments=c.comment_count,
    )


def list_chapters(
    session: Session, series_id: str, *, language: str | None, order: str
) -> list[VolumeGroupOut]:
    """Chapters grouped by volume, preserving the requested chapter order."""
    if session.get(Series, series_id) is None:
        raise NotFoundError(f"series {series_id!r} not found")
    rows = repo.list_chapters(session, series_id, language=language, descending=order != "asc")
    groups: list[VolumeGroupOut] = []
    by_volume: dict[int | None, VolumeGroupOut] = {}
    for row in rows:
        volume = row.chapter.volume
        group = by_volume.get(volume)
        if group is None:
            group = VolumeGroupOut(volume=volume, chapters=[])
            by_volume[volume] = group
            groups.append(group)
        group.chapters.append(to_chapter_out(row))
    return groups


def get_chapter(session: Session, chapter_id: str) -> ChapterDetailOut:
    row = repo.get_chapter(session, chapter_id)
    if row is None:
        raise NotFoundError(f"chapter {chapter_id!r} not found")
    c = row.chapter
    return ChapterDetailOut(
        id=c.id,
        series_id=c.series_id,
        volume=c.volume,
        number=c.number or "",
        title=c.title,
        group=c.group_name,
        language=c.language,
        page_count=c.page_count,
        comments=c.comment_count,
        read=row.read,
        uploaded_at=c.source_uploaded_at or c.created_at,
    )


def _to_recent_update(row: UpdateRow, series: SeriesOut) -> RecentUpdateOut:
    return RecentUpdateOut(
        series=series,
        volume=row.chapter.volume,
        chapter=row.chapter.number or "",
        updated_at=row.updated_at,
    )


def updates(
    session: Session, *, unread_only: bool, cursor: str | None, limit: int
) -> Page[RecentUpdateOut]:
    limit = max(1, min(limit, _MAX_LIMIT))
    rows, next_cursor = repo.recent_updates(
        session, unread_only=unread_only, cursor=cursor, limit=limit
    )
    series_map = repo.get_series_rows(session, [r.chapter.series_id for r in rows])
    items = [
        _to_recent_update(r, to_series_out(series_map[r.chapter.series_id]))
        for r in rows
        if r.chapter.series_id in series_map
    ]
    return Page[RecentUpdateOut](items=items, next_cursor=next_cursor)


def dashboard(session: Session) -> DashboardOut:
    series_count, unread_chapters, reading = repo.dashboard_counts(session)
    recent = updates(session, unread_only=False, cursor=None, limit=12)
    return DashboardOut(
        stats=DashboardStats(series=series_count, unread_chapters=unread_chapters, reading=reading),
        continue_reading=[to_series_out(r) for r in repo.continue_reading(session, limit=6)],
        recent_updates=recent.items,
        recently_added=[to_series_out(r) for r in repo.recently_added(session, limit=12)],
    )


def search(session: Session, q: str, *, limit: int = 20) -> list[SeriesOut]:
    if not q.strip():
        return []
    return [to_series_out(r) for r in repo.search_series(session, q.strip(), limit=limit)]


def related(session: Session, series_id: str, *, limit: int = 12) -> list[SeriesOut]:
    """Other series of the same kind (Related tab)."""
    if session.get(Series, series_id) is None:
        raise NotFoundError(f"series {series_id!r} not found")
    rows = repo.related_series(session, series_id, limit=limit)
    return [to_series_out(r) for r in rows]


def series_art(session: Session, series_id: str) -> SeriesArtOut:
    """Extra art for a series (Art tab). Empty until an art store exists (backlog)."""
    if session.get(Series, series_id) is None:
        raise NotFoundError(f"series {series_id!r} not found")
    return SeriesArtOut(images=[])


_KIND_ROUTE: dict[str, tuple[str, str]] = {
    "manga": ("manga", "Manga"),
    "comic": ("comics", "Comics"),
    "gallery": ("gallery", "Gallery"),
}


def library_summaries(session: Session) -> list[LibrarySummaryOut]:
    """Per-kind storage usage (Home + About). GB rounded; caller hides zero-size."""
    summaries: list[LibrarySummaryOut] = []
    for kind, size_bytes in repo.library_size_by_kind(session):
        meta = _KIND_ROUTE.get(kind)
        if meta is None:
            continue
        route, title = meta
        summaries.append(
            LibrarySummaryOut(key=route, title=title, size_gb=round(size_bytes / 1e9, 1))
        )
    order = {"manga": 0, "comics": 1, "gallery": 2}
    summaries.sort(key=lambda s: order.get(s.key, 9))
    return summaries
