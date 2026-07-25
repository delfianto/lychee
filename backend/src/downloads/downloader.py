"""Chapter downloader → AVIF pipeline.

A download runs in two phases so it can be paused and resumed:

* :func:`plan_downloads` lists the series' remote chapters and inserts one
  ``queued`` :class:`DownloadTask` per pending chapter, stashing the remote
  chapter in ``remote_json`` so it can be fetched later.
* :func:`run_download_queue` drains those rows one at a time — for each, fetch
  page bytes from the provider, encode each to AVIF (discarding the original),
  write to ``<storage>/downloads/<series>/<chapter>`` as an ``avif_dir`` Book,
  and create the Chapter. It commits per chapter (and per page), so a pause
  takes effect at the next chapter boundary and progress is visible live.

Downloaded books live in a "Downloads" library so serving resolves their path
independently of the series' own (scan) library.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from functools import partial
from pathlib import Path
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.media import generate_series_cover
from src.catalog.models import Book, Chapter, Library, Series
from src.downloads.models import DownloadTask
from src.downloads.provider import Provider, RemoteChapter, get_provider
from src.media.encode_pool import encode_pages
from src.media.thumbnails import ThumbnailStore

DOWNLOADS_LIBRARY = "Downloads"


def downloads_library(session: Session, storage_root: Path) -> Library:
    """Get-or-create the library that owns downloaded content."""
    root = str(storage_root / "downloads")
    library = session.scalar(select(Library).where(Library.name == DOWNLOADS_LIBRARY))
    if library is None:
        library = Library(name=DOWNLOADS_LIBRARY, path=root, kind="mixed")
        session.add(library)
        session.flush()
    elif library.path != root:
        library.path = root
    return library


def _number_sort(number: str) -> float | None:
    try:
        return float(number)
    except ValueError:
        return None


def _parse_published(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)  # handles the trailing 'Z' on 3.11+
    except ValueError:
        return None


def _report_page_row(
    session: Session,
    on_progress: Callable[[int, str], None] | None,
    label: str,
    chapter_pct: int,
) -> None:
    """Commit the in-flight chapter row (so /api/downloads sees its progress climb)
    and emit a progress SSE event. Bound per chapter via functools.partial."""
    session.commit()
    if on_progress is not None:
        on_progress(chapter_pct, label)


def _download_chapter(
    session: Session,
    *,
    series: Series,
    library: Library,
    remote: RemoteChapter,
    provider: Provider,
    storage_root: Path,
    task: DownloadTask,
    data_saver: bool = False,
    on_page: Callable[[int], None] | None = None,
) -> Chapter:
    pages = provider.fetch_pages(remote, data_saver=data_saver)
    rel = f"{series.id}/{remote.provider_chapter_id}"
    out_dir = storage_root / "downloads" / rel
    out_dir.mkdir(parents=True, exist_ok=True)

    total = len(pages) or 1
    size = 0
    # content-aware AVIF (discard original), possibly fanned across the encode pool
    for index, data in enumerate(encode_pages(pages)):
        _ = (out_dir / f"{index + 1:03d}.avif").write_bytes(data)
        size += len(data)
        task.progress = int((index + 1) / total * 100)
        if on_page is not None:
            on_page(task.progress)  # publish this chapter's page progress

    book = Book(
        series_id=series.id,
        library_id=library.id,
        path_rel=rel,
        content_kind="avif_dir",
        file_size=size,
        page_count=len(pages),
    )
    session.add(book)
    session.flush()
    chapter = Chapter(
        series_id=series.id,
        book_id=book.id,
        volume=remote.volume,
        number=remote.number,
        number_sort=_number_sort(remote.number),
        title=remote.title,
        language=remote.language,
        group_name=remote.group_name,
        source_uploaded_at=_parse_published(remote.published_at),
        page_count=len(pages),
        provider=provider.id,
        provider_chapter_id=remote.provider_chapter_id,
    )
    session.add(chapter)
    session.flush()
    task.chapter_id = chapter.id
    task.size_bytes = size
    return chapter


def plan_downloads(
    session: Session,
    series: Series,
    provider: Provider,
    *,
    language: str = "en",
    limit: int | None = None,
) -> int:
    """Insert one ``queued`` DownloadTask per pending remote chapter and return the
    count added. A chapter is pending when it is neither already in the library nor
    already carried by a live (queued/downloading/paused) row, so re-planning a
    partially-finished or paused series is a safe no-op for what's in flight.
    """
    remotes = provider.list_chapters(series.provider_series_id or "", language=language)
    local = set(
        session.scalars(select(Chapter.number).where(Chapter.series_id == series.id))
    )
    in_flight = {
        row.chapter_label
        for row in session.scalars(
            select(DownloadTask).where(
                DownloadTask.series_id == series.id,
                DownloadTask.status.in_(("queued", "downloading", "paused")),
            )
        )
    }
    pending = [remote for remote in remotes if remote.number not in local]
    if limit is not None:
        pending = pending[:limit]

    queued = 0
    for remote in pending:
        label = f"Ch. {remote.number}"
        if label in in_flight:
            continue
        session.add(
            DownloadTask(
                series_id=series.id,
                chapter_label=label,
                status="queued",
                provider=provider.id,
                remote_json=cast("dict[str, object]", asdict(remote)),
            )
        )
        queued += 1
    session.commit()
    return queued


def run_download_queue(
    session: Session,
    series_id: str,
    storage_root: Path,
    *,
    data_saver: bool = False,
    on_progress: Callable[[int, str], None] | None = None,
) -> int:
    """Drain the series' ``queued`` rows one at a time, returning the count processed.

    Each row is claimed (``downloading``), its chapter downloaded, then marked
    ``done``/``failed``; ``paused`` rows are skipped, so pausing simply stops the
    drain from picking a chapter up. Safe to run serially (the task queue uses a
    single worker), which is why claiming a row need not be atomic.
    """
    series = session.get(Series, series_id)
    if series is None:
        return 0
    provider = get_provider(series.provider or "")
    if provider is None:
        return 0
    library = downloads_library(session, storage_root)
    store = ThumbnailStore(storage_root / "thumbnails")

    processed = 0
    while True:
        row = session.scalar(
            select(DownloadTask)
            .where(DownloadTask.series_id == series_id, DownloadTask.status == "queued")
            .order_by(DownloadTask.created_at)
        )
        if row is None:
            break
        row.status = "downloading"
        row.progress = 0
        session.commit()  # claim the row — it shows as "downloading" in /api/downloads at once
        try:
            if not row.remote_json:
                raise ValueError("queued download is missing chapter data")
            remote = RemoteChapter(**cast("dict[str, Any]", row.remote_json))
            _download_chapter(
                session,
                series=series,
                library=library,
                remote=remote,
                provider=provider,
                storage_root=storage_root,
                task=row,
                data_saver=data_saver,
                on_page=partial(_report_page_row, session, on_progress, row.chapter_label),
            )
            row.status = "done"
            row.progress = 100
        except Exception as exc:  # noqa: BLE001 - record failure on the row, keep draining
            row.status = "failed"
            row.error = str(exc)
        session.commit()  # persist the row's final status so the table settles
        if row.status == "done":
            _ = generate_series_cover(session, store, series_id)  # warm cover from the new pages
        processed += 1
        if on_progress is not None:
            on_progress(100, row.chapter_label)
    return processed
