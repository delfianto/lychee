"""Catalog services — parse query params and assemble API responses."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.catalog import repository as repo
from src.catalog.models import Series
from src.catalog.repository import ChapterRow, SeriesFilters, SeriesRow, UpdateRow
from src.catalog.schema import (
    ChapterDetailOut,
    ChapterOut,
    DashboardOut,
    DashboardStats,
    RecentUpdateOut,
    SeriesOut,
    TagOut,
    VolumeGroupOut,
)
from src.core.exceptions import NotFoundError
from src.core.schema import Page

_MAX_LIMIT = 100


def cover_url(series_id: str) -> str:
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
        cover_url=cover_url(s.id),
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
        favorite=s.favorite,
        kind=s.kind,
        image_count=s.image_count,
        source=s.source,
        characters=s.characters_json,
        library_status=s.library_status,
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
