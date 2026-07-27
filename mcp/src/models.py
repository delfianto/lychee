"""Pydantic models for the subset of the backend's REST contract this server
consumes. Hand-written rather than generated from backend/openapi.json — only
a handful of endpoints are needed for the batch tools (see notes/plan.md PART
J, "Open before starting" for revisiting this if the tool surface grows).

Mirrors the backend's CamelModel convention (src/core/schema.py): camelCase
on the wire, snake_case in Python.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


def _to_camel(name: str) -> str:
    head, *tail = name.split("_")
    return head + "".join(part.capitalize() for part in tail)


class CamelModel(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)


class Tag(CamelModel):
    id: str
    name: str
    group: str


class Series(CamelModel):
    id: str
    title: str
    cover_url: str
    authors: list[str] = []
    artists: list[str] = []
    status: str
    content_rating: str
    demographic: str
    tags: list[Tag] = []
    chapter_count: int
    unread_count: int
    year: int | None = None
    description: str | None = None
    favorite: bool = False
    kind: str | None = None
    library_status: str | None = None
    provider: str | None = None
    available_chapters: int = 0
    rating: float | None = None
    user_rating: float | None = None
    source: str | None = None
    image_count: int | None = None


class SeriesPage(CamelModel):
    items: list[Series] = []
    next_cursor: str | None = None


class TaxonomyItem(CamelModel):
    id: str
    name: str
    category: str
    uses: int
    enabled: bool
    system: bool


class TaxonomyPage(CamelModel):
    items: list[TaxonomyItem] = []
    total: int
    page: int
    page_size: int


class DownloadTask(CamelModel):
    id: str
    series: Series
    chapter: str
    status: str
    progress: int
    phase: str | None = None
    detail: str | None = None
    size_bytes: int | None = None


class LibraryRow(CamelModel):
    id: str
    name: str
    path: str
    kind: str
    enabled: bool
    series_count: int
    last_scan: str | None = None


class TaskOut(CamelModel):
    id: str
    kind: str
    label: str
    status: str
    progress: int
    detail: str | None = None
    result: dict[str, object] | None = None
