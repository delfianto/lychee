"""Library scan pipeline (ADR 07) — walk → resolve → diff → reconcile.

v1 does a periodic/manual full scan of a library root. First-level directories are
**Series**; archives and image-only folders beneath are **Books**; a loose archive
directly under the root is a one-shot Series. Each Book yields one **Chapter** (the
book + its full page range). Move/rename safety comes from soft-delete + a
``(file_size, partial_hash)`` restore hint. Covers are generated lazily on first
request, so no thumbnail job is enqueued here.

Deferred (follow-ups): filesystem watcher, content-type sniffing (extension only
for now), embedded ComicInfo/OPF metadata, FTS sync (B6), RAR/7z/PDF/EPUB
containers, and multi-chapter archives.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.catalog.models import Book, Chapter, Library, Series
from src.core.exceptions import BadRequestError, LycheeError
from src.core.logging import get_logger
from src.core.persistence.base_model import utc_now
from src.ingest.parser import parse
from src.media.containers import IMAGE_EXTS, open_container

logger = get_logger(__name__)

_ARCHIVE_KINDS = {".cbz": "cbz", ".zip": "zip"}  # extended as containers land
_HASH_CHUNK = 64 * 1024


@dataclass
class ScanSummary:
    """Counts from one scan pass."""

    series_added: int = 0
    books_added: int = 0
    books_updated: int = 0
    books_removed: int = 0


@dataclass
class _Candidate:
    path: Path  # absolute path on disk
    rel: str  # path relative to the library root (stored on Book)
    kind: str  # content_kind
    segments: list[str]  # path parts below the series folder + name (for the parser)


def _is_image(name: str) -> bool:
    return Path(name).suffix.lower() in IMAGE_EXTS


def _archive_kind(name: str) -> str | None:
    return _ARCHIVE_KINDS.get(Path(name).suffix.lower())


def _signature(path: Path) -> tuple[int, float, str]:
    """Return (size_bytes, mtime, partial_hash) for a file or an image directory."""
    digest = hashlib.sha1()
    if path.is_dir():
        images = sorted(p for p in path.iterdir() if p.is_file() and _is_image(p.name))
        size = 0
        mtime = path.stat().st_mtime
        for image in images:
            stat = image.stat()
            size += stat.st_size
            mtime = max(mtime, stat.st_mtime)
            digest.update(f"{image.name}:{stat.st_size};".encode())
        return size, mtime, digest.hexdigest()[:40]

    stat = path.stat()
    with path.open("rb") as handle:
        digest.update(handle.read(_HASH_CHUNK))
        if stat.st_size > _HASH_CHUNK:
            _ = handle.seek(max(0, stat.st_size - _HASH_CHUNK))
            digest.update(handle.read(_HASH_CHUNK))
    digest.update(str(stat.st_size).encode())
    return stat.st_size, stat.st_mtime, digest.hexdigest()[:40]


def _candidate(item: Path, root: Path, series_dir: Path, kind: str) -> _Candidate:
    parts = list(item.relative_to(series_dir).parts) or [series_dir.name]
    return _Candidate(path=item, rel=str(item.relative_to(root)), kind=kind, segments=parts)


def _resolve_books(series_dir: Path, root: Path) -> list[_Candidate]:
    """Walk a series folder (ADR 05 hybrid rule): image-only dir → book; archive →
    book; a folder holding archives/sub-folders is a grouping level (recurse)."""
    found: list[_Candidate] = []

    def visit(directory: Path) -> None:
        entries = sorted(p for p in directory.iterdir() if not p.name.startswith("."))
        if any(e.is_file() and _is_image(e.name) for e in entries):
            found.append(_candidate(directory, root, series_dir, "image_dir"))
            return  # its images are the pages; don't recurse
        for entry in entries:
            if entry.is_file() and (kind := _archive_kind(entry.name)):
                found.append(_candidate(entry, root, series_dir, kind))
            elif entry.is_dir():
                visit(entry)

    visit(series_dir)
    return found


def _series_kind(library: Library) -> str:
    return library.kind if library.kind in {"manga", "comic", "gallery"} else "manga"


def _page_count(candidate: _Candidate) -> int | None:
    """Open the container to count pages; None if it can't be read (skip it)."""
    try:
        with open_container(candidate.path, candidate.kind) as container:
            return container.page_count()
    except LycheeError as exc:
        logger.warning("scan_skip_unreadable", path=candidate.rel, error=str(exc))
        return None


def scan_library(session: Session, library: Library) -> ScanSummary:
    """Full scan of one library: reconcile its Series/Book/Chapter rows with disk."""
    root = Path(library.path)
    if not root.is_dir():
        raise BadRequestError(f"library path not found: {root}")

    summary = ScanSummary()
    existing = {
        book.path_rel: book
        for book in session.scalars(
            select(Book).where(Book.library_id == library.id, Book.deleted_at.is_(None))
        )
    }
    seen: set[str] = set()

    for entry in sorted(p for p in root.iterdir() if not p.name.startswith(".")):
        if entry.is_dir():
            candidates = _resolve_books(entry, root)
            if candidates:
                _ingest_series(session, library, entry.name, candidates, existing, seen, summary)
        elif entry.is_file() and (kind := _archive_kind(entry.name)):
            title = Path(entry.name).stem
            oneshot = [_candidate(entry, root, root, kind)]
            _ingest_series(session, library, title, oneshot, existing, seen, summary)

    for path_rel, book in existing.items():
        if path_rel not in seen:
            book.deleted_at = utc_now()
            # Drop the derived chapters (progress on them cascades away). Proper
            # progress migration on restore is a follow-up (ADR 07 tryRestore).
            _ = session.execute(delete(Chapter).where(Chapter.book_id == book.id))
            summary.books_removed += 1

    library.last_scan_at = utc_now()
    session.flush()
    return summary


def _ingest_series(
    session: Session,
    library: Library,
    title: str,
    candidates: list[_Candidate],
    existing: dict[str, Book],
    seen: set[str],
    summary: ScanSummary,
) -> None:
    kind = _series_kind(library)
    series = session.scalar(
        select(Series).where(Series.library_id == library.id, Series.title == title)
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
        summary.series_added += 1

    chapters: list[Chapter] = []
    for candidate in candidates:
        book = _reconcile_book(session, library, series, candidate, existing, seen, summary)
        if book is None:
            continue
        if kind == "gallery":
            series.image_count = book.page_count
        else:
            chapters.append(_sync_chapter(session, series, book, candidate, title, kind))

    if chapters:
        _order_chapters(chapters)


def _reconcile_book(
    session: Session,
    library: Library,
    series: Series,
    candidate: _Candidate,
    existing: dict[str, Book],
    seen: set[str],
    summary: ScanSummary,
) -> Book | None:
    prior = existing.get(candidate.rel)
    size, mtime, partial_hash = _signature(candidate.path)

    if prior is not None:
        seen.add(candidate.rel)
        if prior.file_size == size and _same_mtime(prior, mtime):
            return prior  # unchanged — skip the container open
        pages = _page_count(candidate)
        if pages is None:
            return prior
        prior.file_size = size
        prior.partial_hash = partial_hash
        prior.page_count = pages
        prior.file_last_modified = _to_dt(mtime)
        summary.books_updated += 1
        return prior

    pages = _page_count(candidate)
    if pages is None:
        return None

    restored = session.scalar(
        select(Book).where(
            Book.library_id == library.id,
            Book.deleted_at.is_not(None),
            Book.file_size == size,
            Book.partial_hash == partial_hash,
        )
    )
    book = restored or Book(series_id=series.id, library_id=library.id)
    book.series_id = series.id
    book.path_rel = candidate.rel
    book.content_kind = candidate.kind
    book.file_size = size
    book.partial_hash = partial_hash
    book.page_count = pages
    book.file_last_modified = _to_dt(mtime)
    book.deleted_at = None
    if restored is None:
        session.add(book)
    session.flush()
    seen.add(candidate.rel)
    summary.books_added += 1
    return book


def _sync_chapter(
    session: Session, series: Series, book: Book, candidate: _Candidate, title: str, kind: str
) -> Chapter:
    parsed = parse(candidate.segments, title, kind)
    chapter = session.scalar(select(Chapter).where(Chapter.book_id == book.id))
    if chapter is None:
        chapter = Chapter(series_id=series.id, book_id=book.id)
        session.add(chapter)
    chapter.series_id = series.id
    chapter.volume = parsed.volume
    chapter.number = parsed.number
    chapter.number_sort = parsed.number_sort
    chapter.title = parsed.label if parsed.special else None
    chapter.page_start = 0
    chapter.page_count = book.page_count
    session.flush()
    return chapter


def _order_chapters(chapters: list[Chapter]) -> None:
    """Assign a number_sort to chapters that lacked one (base-less specials, volume
    -only books), placing them after their sorted neighbours (ADR 06 §6 / ADR 07)."""
    ordered = sorted(chapters, key=lambda c: (c.number_sort is None, c.number_sort or 0.0))
    running = 0.0
    for chapter in ordered:
        if chapter.number_sort is None:
            running += 1.0
            chapter.number_sort = running
            if chapter.number is None:
                chapter.number = str(int(running))
        else:
            running = max(running, chapter.number_sort)


def _same_mtime(book: Book, mtime: float) -> bool:
    stored = book.file_last_modified
    if stored is None:
        return False
    # SQLite returns our UTC timestamps tz-naive; interpret them as UTC so the
    # epoch comparison is correct (a 2s tolerance covers FS mtime granularity).
    epoch = (stored if stored.tzinfo else stored.replace(tzinfo=UTC)).timestamp()
    return abs(epoch - mtime) < 2.0


def _to_dt(mtime: float) -> datetime:
    return datetime.fromtimestamp(mtime, tz=UTC)
