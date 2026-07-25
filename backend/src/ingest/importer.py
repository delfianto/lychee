"""Local import: transcode a container file or series folder from disk to AVIF.

Unlike the scanner (which registers in-place originals), import reads a source path
the admin points at, re-encodes every page to AVIF at the configured quality, and
writes an ``avif_dir`` Book under ``storage/imports/`` into a managed "Imports"
library. It reuses the scanner's book walk + filename parse and warms the cover
eagerly (PART G / G1). Runs on the background task queue.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.media import generate_series_cover
from src.catalog.models import Book, Chapter, Library, Series
from src.core.exceptions import BadRequestError, LycheeError
from src.core.logging import get_logger
from src.ingest.scanner import Candidate, order_chapters, resolve_books, sync_chapter
from src.media.avif import encode_bytes
from src.media.containers import open_container
from src.media.thumbnails import ThumbnailStore

logger = get_logger(__name__)

IMPORTS_LIBRARY = "Imports"
_ARCHIVE_EXTS = {".cbz": "cbz", ".zip": "zip"}  # container files import accepts (matches the reader)
_KINDS = {"manga", "comic", "gallery"}


def imports_library(session: Session, storage_root: Path) -> Library:
    """Get-or-create the managed library that owns transcoded imports."""
    root = str(storage_root / "imports")
    library = session.scalar(select(Library).where(Library.name == IMPORTS_LIBRARY))
    if library is None:
        library = Library(name=IMPORTS_LIBRARY, path=root, kind="mixed")
        session.add(library)
        session.flush()
    elif library.path != root:
        library.path = root
    return library


def _get_or_create_series(session: Session, library: Library, title: str, kind: str) -> Series:
    series = session.scalar(
        select(Series).where(Series.library_id == library.id, Series.path_rel == title)
    )
    if series is None:
        series = Series(
            library_id=library.id,
            kind=kind,
            title=title,
            sort_title=title.lower(),
            path_rel=title,
        )
        session.add(series)
        session.flush()
    return series


def _book_key(candidate: Candidate) -> str:
    """A stable, filesystem-safe subdir name for a book, so re-import is idempotent."""
    return hashlib.sha1(candidate.rel.encode()).hexdigest()[:16]


def _import_book(
    session: Session,
    library: Library,
    series: Series,
    candidate: Candidate,
    storage_root: Path,
    *,
    quality: int,
) -> Book | None:
    """Transcode one source book's pages to AVIF and register it. Returns the new Book,
    or None if it was already imported (idempotent) or the source can't be read."""
    rel = f"{series.id}/{_book_key(candidate)}"
    already = session.scalar(
        select(Book.id).where(
            Book.library_id == library.id, Book.path_rel == rel, Book.deleted_at.is_(None)
        )
    )
    if already is not None:
        return None  # already imported — nothing to do this run
    out_dir = storage_root / "imports" / rel
    try:
        with open_container(candidate.path, candidate.kind) as container:
            count = container.page_count()
            out_dir.mkdir(parents=True, exist_ok=True)
            size = 0
            for index in range(count):
                data = encode_bytes(container.read_page(index), quality=quality)
                _ = (out_dir / f"{index + 1:03d}.avif").write_bytes(data)
                size += len(data)
    except LycheeError as exc:
        logger.warning("import_skip_unreadable", path=str(candidate.path), error=str(exc))
        return None
    book = Book(
        series_id=series.id,
        library_id=library.id,
        path_rel=rel,
        content_kind="avif_dir",
        file_size=size,
        page_count=count,
    )
    session.add(book)
    session.flush()
    return book


def _resolve_source(source: Path) -> tuple[str, list[Candidate]]:
    """(series title, source book candidates) for an import path (a file or a folder)."""
    if source.is_file():
        kind = _ARCHIVE_EXTS.get(source.suffix.lower())
        if kind is None:
            raise BadRequestError(f"unsupported import file: {source.name}")
        candidate = Candidate(path=source, rel=source.name, kind=kind, segments=[source.name])
        return source.stem, [candidate]
    if source.is_dir():
        candidates = resolve_books(source, source)
        if not candidates:
            raise BadRequestError(f"no importable content found under {source.name}")
        return source.name, candidates
    raise BadRequestError(f"unsupported import path: {source}")


def import_path(
    session: Session,
    source: Path,
    *,
    kind: str,
    storage_root: Path,
    quality: int,
    on_progress: Callable[[int, str], None] | None = None,
) -> dict[str, int]:
    """Import a container file or series folder, transcoding its pages to AVIF.

    Creates/reuses one series in the managed "Imports" library; each source book
    becomes an ``avif_dir`` Book (+ Chapter). Commits per book so progress is visible,
    then warms the series cover. Returns ``{"booksImported": n}``.
    """
    if not source.exists():
        raise BadRequestError(f"import path not found: {source}")
    series_kind = kind if kind in _KINDS else "manga"
    library = imports_library(session, storage_root)
    store = ThumbnailStore(storage_root / "thumbnails")

    title, candidates = _resolve_source(source)
    series = _get_or_create_series(session, library, title, series_kind)

    chapters: list[Chapter] = []
    imported = 0
    total = len(candidates) or 1
    for index, candidate in enumerate(candidates, start=1):
        book = _import_book(session, library, series, candidate, storage_root, quality=quality)
        if book is not None:
            imported += 1
            if series_kind == "gallery":
                series.image_count = book.page_count
            else:
                chapters.append(sync_chapter(session, series, book, candidate, title, series_kind))
        session.commit()
        if on_progress is not None:
            on_progress(round(index / total * 100), candidate.segments[-1])

    if chapters:
        order_chapters(chapters)
        session.commit()
    _ = generate_series_cover(session, store, series.id)
    return {"booksImported": imported}
