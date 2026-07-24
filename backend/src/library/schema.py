"""Library API schemas."""

from __future__ import annotations

from src.core.schema import CamelModel, UtcDatetime


class LibraryOut(CamelModel):
    id: str
    name: str
    path: str
    kind: str
    enabled: bool
    series_count: int
    last_scan: UtcDatetime | None = None


class LibraryCreate(CamelModel):
    name: str
    path: str
    kind: str = "manga"


class LibraryUpdate(CamelModel):
    name: str | None = None
    path: str | None = None
    enabled: bool | None = None


class ScanResultOut(CamelModel):
    series_added: int
    books_added: int
    books_updated: int
    books_removed: int
