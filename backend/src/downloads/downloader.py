"""Chapter downloader → AVIF pipeline (ADR 13, ADR 19).

For each remote chapter: fetch page bytes from the provider, encode each to AVIF
(discarding the original — ADR 19), write to ``<storage>/downloads/<series>/<chapter>``
as an ``avif_dir`` Book, and create the Chapter. Downloaded books live in a
"Downloads" library so serving resolves their path independently of the series'
own (scan) library. Synchronous in v1; a background task runner + live progress
is a follow-up.
"""

from __future__ import annotations

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


def _download_chapter(
    session: Session,
    *,
    series: Series,
    library: Library,
    remote: RemoteChapter,
    provider: Provider,
    storage_root: Path,
    task: DownloadTask,
) -> Chapter:
    pages = provider.fetch_pages(remote)
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
) -> list[DownloadTask]:
    """Download every remote chapter of ``series`` not already present."""
    library = downloads_library(session, storage_root)
    remotes = provider.list_chapters(series.provider_series_id or "", language=language)
    existing = {
        c.number for c in session.scalars(select(Chapter).where(Chapter.series_id == series.id))
    }

    tasks: list[DownloadTask] = []
    for remote in remotes:
        if remote.number in existing:
            continue
        task = DownloadTask(
            series_id=series.id, chapter_label=f"Ch. {remote.number}", status="downloading"
        )
        session.add(task)
        session.flush()
        try:
            _download_chapter(
                session,
                series=series,
                library=library,
                remote=remote,
                provider=provider,
                storage_root=storage_root,
                task=task,
            )
            task.status = "done"
            task.progress = 100
        except Exception as exc:  # noqa: BLE001 - record failure on the task, keep going
            task.status = "failed"
            task.error = str(exc)
        tasks.append(task)
        if limit is not None and len(tasks) >= limit:
            break
    session.flush()
    return tasks
