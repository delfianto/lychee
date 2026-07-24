"""Catalog API schemas — camelCase response models mirroring frontend/src/types.

Timestamps are returned as ISO-8601 (pydantic serializes ``datetime``); the
frontend renders relative labels ("2h ago"). Image fields are API paths, never
filesystem paths (ADR 09 / B0).
"""

from __future__ import annotations

from datetime import datetime

from src.core.schema import CamelModel


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
    favorite: bool = False
    kind: str | None = None
    image_count: int | None = None
    source: str | None = None
    characters: list[str] | None = None
    library_status: str | None = None


class ChapterOut(CamelModel):
    id: str
    volume: int | None
    number: str
    title: str | None = None
    group: str | None = None
    language: str
    uploaded_at: datetime | None = None
    read: bool
    comments: int


class VolumeGroupOut(CamelModel):
    volume: int | None
    chapters: list[ChapterOut]


class RecentUpdateOut(CamelModel):
    series: SeriesOut
    volume: int | None
    chapter: str
    updated_at: datetime


class DashboardStats(CamelModel):
    series: int
    unread_chapters: int
    reading: int


class DashboardOut(CamelModel):
    stats: DashboardStats
    continue_reading: list[SeriesOut]
    recent_updates: list[RecentUpdateOut]
    recently_added: list[SeriesOut]
