"""Catalog API schemas — camelCase response models mirroring frontend/src/types.

Timestamps are returned as ISO-8601 (pydantic serializes ``datetime``); the
frontend renders relative labels ("2h ago"). Image fields are API paths, never
filesystem paths (ADR 09 / B0).
"""

from __future__ import annotations

from src.core.schema import CamelModel, UtcDatetime


class TagOut(CamelModel):
    id: str
    name: str
    group: str


class SeriesOut(CamelModel):
    id: str
    title: str
    cover_url: str
    authors: list[str]
    artists: list[str]
    status: str
    content_rating: str
    demographic: str
    tags: list[TagOut]
    chapter_count: int
    unread_count: int
    year: int | None = None
    description: str | None = None
    last_read_chapter: float | None = None
    total_chapters: int | None = None
    origin_country: str | None = None
    rating: float | None = None
    user_rating: float | None = None
    favorite: bool = False
    kind: str | None = None
    image_count: int | None = None
    source: str | None = None
    characters: list[str] | None = None
    library_status: str | None = None
    provider: str | None = None  # matched metadata provider slug, or null if unmatched
    available_chapters: int = 0  # remote chapters not yet local (from the last sync)


class SeriesUpdate(CamelModel):
    """Detail action-row edits (all optional; absent fields are left unchanged)."""

    favorite: bool | None = None
    library_status: str | None = None
    rating: float | None = None  # the user's personal rating (→ Series.user_rating)


class MangaMatchOut(CamelModel):
    """A provider search candidate for matching a local series (PART F/M2)."""

    provider_series_id: str
    title: str
    year: int | None = None
    status: str | None = None
    cover_url: str | None = None


class MatchRequest(CamelModel):
    provider_series_id: str
    provider: str = "mangadex"


class ChapterOut(CamelModel):
    id: str
    volume: int | None
    number: str
    title: str | None = None
    group: str | None = None
    language: str
    uploaded_at: UtcDatetime | None = None
    read: bool
    comments: int


class ChapterDetailOut(CamelModel):
    id: str
    series_id: str
    volume: int | None
    number: str
    title: str | None = None
    group: str | None = None
    language: str
    page_count: int
    comments: int
    read: bool
    uploaded_at: UtcDatetime | None = None


class VolumeGroupOut(CamelModel):
    volume: int | None
    chapters: list[ChapterOut]


class RecentUpdateOut(CamelModel):
    series: SeriesOut
    volume: int | None
    chapter: str
    updated_at: UtcDatetime


class SeriesArtOut(CamelModel):
    images: list[str]


class LibrarySummaryOut(CamelModel):
    key: str
    title: str
    size_gb: float


class DashboardStats(CamelModel):
    series: int
    unread_chapters: int
    reading: int


class DashboardOut(CamelModel):
    stats: DashboardStats
    continue_reading: list[SeriesOut]
    recent_updates: list[RecentUpdateOut]
    recently_added: list[SeriesOut]
