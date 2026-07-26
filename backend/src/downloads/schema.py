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
    phase: str | None = None  # fetching | encoding while in progress
    detail: str | None = None  # e.g. "12/40"
    size_bytes: int | None = None


class DownloadCreate(CamelModel):
    """Start a series download, or run a bulk queue action.

    * Queue work: set ``series_id`` (optional ``provider_chapter_ids``).
    * Bulk: set ``action`` to ``pause-all`` | ``cancel-all`` | ``resume-all``
      (``series_id`` ignored).
    """

    series_id: str | None = None
    # When set, only these remote chapters are queued; omit to plan every missing chapter.
    provider_chapter_ids: list[str] | None = None
    # pause-all | cancel-all | resume-all — mutates the queue without enqueueing a series.
    action: str | None = None
