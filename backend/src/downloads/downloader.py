"""Chapter downloader → AVIF pipeline.

For each remote chapter: fetch page bytes from the provider, encode each to AVIF
(discarding the original), write to ``<storage>/downloads/<series>/<chapter>`` as
an ``avif_dir`` Book, and create the Chapter. Downloaded books live in a
"Downloads" library so serving resolves their path independently of the series'
own (scan) library. Runs on the background task queue, committing per chapter so
progress is visible mid-download.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from functools import partial
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.models import Book, Chapter, Library, Series
from src.downloads.models import DownloadTask
from src.downloads.provider import Provider, RemoteChapter
from src.media.avif import encode_bytes

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


def _report_page(
    session: Session,
    on_progress: Callable[[int, str], None] | None,
    index: int,
    total: int,
    number: str,
    chapter_pct: int,
) -> None:
    """Commit the in-flight chapter row (so /api/downloads sees it climb) and emit an
    overall-progress SSE event. Bound per chapter via functools.partial."""
    session.commit()
    if on_progress is not None:
        overall = round(((index - 1) + chapter_pct / 100) / total * 100)
        on_progress(overall, f"Ch. {number}")


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
    for index, raw in enumerate(pages):
        data = encode_bytes(raw)  # content-aware AVIF (discard original)
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


def download_series(
    session: Session,
    series: Series,
    provider: Provider,
    storage_root: Path,
    *,
    language: str = "en",
    limit: int | None = None,
    data_saver: bool = False,
    on_progress: Callable[[int, str], None] | None = None,
) -> list[DownloadTask]:
    """Download every remote chapter of ``series`` not already present.

    ``on_progress(percent, label)`` fires after each chapter so callers can
    surface live download progress (SSE).
    """
    library = downloads_library(session, storage_root)
    remotes = provider.list_chapters(series.provider_series_id or "", language=language)
    existing = {
        c.number for c in session.scalars(select(Chapter).where(Chapter.series_id == series.id))
    }
    pending = [remote for remote in remotes if remote.number not in existing]
    if limit is not None:
        pending = pending[:limit]
    total = len(pending)

    tasks: list[DownloadTask] = []
    for index, remote in enumerate(pending, start=1):
        task = DownloadTask(
            series_id=series.id, chapter_label=f"Ch. {remote.number}", status="downloading"
        )
        session.add(task)
        session.flush()
        session.commit()  # the row shows up as "downloading" in /api/downloads at once
        try:
            _download_chapter(
                session,
                series=series,
                library=library,
                remote=remote,
                provider=provider,
                storage_root=storage_root,
                task=task,
                data_saver=data_saver,
                on_page=partial(_report_page, session, on_progress, index, total, remote.number),
            )
            task.status = "done"
            task.progress = 100
        except Exception as exc:  # noqa: BLE001 - record failure on the task, keep going
            task.status = "failed"
            task.error = str(exc)
        session.commit()  # persist the row's final status so the table settles
        tasks.append(task)
        if on_progress is not None:
            on_progress(round(index / total * 100), f"Ch. {remote.number}")
    return tasks
