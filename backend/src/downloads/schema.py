"""Downloads API schemas (Settings → Downloads)."""

from __future__ import annotations

from src.catalog.schema import SeriesOut
from src.core.schema import CamelModel


class DownloadTaskOut(CamelModel):
    id: str
    series: SeriesOut
    chapter: str
    status: str
    progress: int
    size_bytes: int | None = None


class DownloadCreate(CamelModel):
    series_id: str
