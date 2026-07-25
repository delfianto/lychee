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

from src.catalog.media import generate_series_cover, write_series_cover
from src.catalog.metadata import reconcile_tags
from src.catalog.models import Book, Chapter, Library, Series, SeriesCredit
from src.core.exceptions import BadRequestError, LycheeError
from src.core.logging import get_logger
from src.ingest.parser import PatternResult, parse_pattern
from src.ingest.scanner import Candidate, order_chapters, resolve_books, sync_chapter
from src.media.containers import open_container, write_cbz
from src.media.encode_pool import encode_pages
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


def _get_or_create_series(
    session: Session, library: Library, *, path_rel: str, title: str, kind: str
) -> Series:
    """Get-or-create by ``path_rel`` (stable source identity); ``title`` is the display
    name (from the filename pattern, or the source name)."""
    series = session.scalar(
        select(Series).where(Series.library_id == library.id, Series.path_rel == path_rel)
    )
    if series is None:
        series = Series(
            library_id=library.id,
            kind=kind,
            title=title,
            sort_title=title.lower(),
            path_rel=path_rel,
        )
        session.add(series)
        session.flush()
    return series


def _apply_series_fields(session: Session, series: Series, result: PatternResult) -> None:
    """Apply series-level pattern fields (year + author/artist credits), deduping credits
    so a re-import doesn't violate the (series, name, role) unique constraint."""
    if result.year is not None:
        series.year = result.year
    existing = {
        (credit.name, credit.role)
        for credit in session.scalars(
            select(SeriesCredit).where(SeriesCredit.series_id == series.id)
        )
    }
    for role, name in (("author", result.author), ("artist", result.artist)):
        if name and (name, role) not in existing:
            session.add(SeriesCredit(series_id=series.id, name=name, role=role))
            existing.add((name, role))
    if result.tags:
        linked = {tag.id for tag in series.tags}
        for tag in reconcile_tags(session, [(name, "genre") for name in result.tags]):
            if tag.id not in linked:
                series.tags.append(tag)
                linked.add(tag.id)


def _import_chapter(
    session: Session,
    series: Series,
    book: Book,
    candidate: Candidate,
    title: str,
    kind: str,
    pattern: str,
) -> Chapter:
    """Create/update the book's Chapter from the token pattern when it matches the
    filename, else the built-in filename parser."""
    result = parse_pattern(candidate.segments[-1], pattern) if pattern else None
    if result is None:
        return sync_chapter(session, series, book, candidate, title, kind)
    chapter = session.scalar(select(Chapter).where(Chapter.book_id == book.id))
    if chapter is None:
        chapter = Chapter(series_id=series.id, book_id=book.id)
        session.add(chapter)
    chapter.series_id = series.id
    chapter.volume = result.volume
    chapter.number = result.number
    chapter.number_sort = result.number_sort
    chapter.title = result.title
    chapter.group_name = result.group
    if result.language:
        chapter.language = result.language
    chapter.page_start = 0
    chapter.page_count = book.page_count
    session.flush()
    return chapter


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
    rel = f"{series.id}/{_book_key(candidate)}.cbz"
    already = session.scalar(
        select(Book.id).where(
            Book.library_id == library.id, Book.path_rel == rel, Book.deleted_at.is_(None)
        )
    )
    if already is not None:
        return None  # already imported — nothing to do this run
    try:
        with open_container(candidate.path, candidate.kind) as container:
            raws = [container.read_page(index) for index in range(container.page_count())]
    except LycheeError as exc:
        logger.warning("import_skip_unreadable", path=str(candidate.path), error=str(exc))
        return None
    # transcode to AVIF at the configured quality (possibly across the encode pool) and
    # pack the pages into a stored CBZ
    dest = storage_root / "imports" / rel
    page_count, size = write_cbz(dest, encode_pages(raws, quality=quality))
    book = Book(
        series_id=series.id,
        library_id=library.id,
        path_rel=rel,
        content_kind="cbz",
        file_size=size,
        page_count=page_count,
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
    filename_pattern: str = "",
    title: str | None = None,
    on_progress: Callable[[int, str], None] | None = None,
) -> dict[str, int]:
    """Import a container file or series folder, transcoding its pages to AVIF.

    Creates/reuses one series in the managed "Imports" library; each source book
    becomes a stored-CBZ Book (+ Chapter). When ``filename_pattern`` is set, it fills
    series/chapter/volume/title/credits from each filename (else the built-in parser).
    ``title`` overrides the series name + identity (uploads pass a batch title, since
    their staging dir has no meaningful name). Commits per book so progress is visible,
    then warms the series cover. Returns ``{"booksImported": n}``.
    """
    if not source.exists():
        raise BadRequestError(f"import path not found: {source}")
    series_kind = kind if kind in _KINDS else "manga"
    library = imports_library(session, storage_root)
    store = ThumbnailStore(storage_root / "thumbnails")

    source_name, candidates = _resolve_source(source)
    # A pattern match on the first book can name the series (+ its year/credits); failing
    # that, an explicit ``title`` (uploads) or the source name. The identity keeps a
    # re-import / re-upload of the same series from duplicating it.
    first = (
        parse_pattern(candidates[0].segments[-1], filename_pattern)
        if filename_pattern and candidates
        else None
    )
    display_title = (first.series if first else None) or title or source_name
    identity = display_title if title is not None else source_name
    series = _get_or_create_series(
        session, library, path_rel=identity, title=display_title, kind=series_kind
    )
    if first is not None:
        _apply_series_fields(session, series, first)

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
                chapters.append(
                    _import_chapter(
                        session, series, book, candidate, display_title, series_kind, filename_pattern
                    )
                )
        session.commit()
        if on_progress is not None:
            on_progress(round(index / total * 100), candidate.segments[-1])

    if chapters:
        order_chapters(chapters)
        session.commit()
    # write a portable Cover.avif beside the series' books, then derive the grid thumbnail
    _ = write_series_cover(session, series.id, storage_root / "imports" / series.id)
    _ = generate_series_cover(session, store, series.id)
    return {"booksImported": imported}
