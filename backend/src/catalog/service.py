"""Catalog services — parse query params and assemble API responses."""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.catalog import repository as repo
from src.catalog.repository import SeriesFilters, SeriesRow
from src.catalog.schema import SeriesOut, TagOut
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
