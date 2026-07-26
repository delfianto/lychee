"""Library scan pipeline — walk → resolve → diff → reconcile.

v1 does a periodic/manual full scan of a library root. First-level directories are
**Series**; archives and image-only folders beneath are **Books**; a loose archive
directly under the root is a one-shot Series. Each Book yields one **Chapter** (the
book + its full page range). For **gallery** libraries the top level is instead the
**artist/model** and each folder/archive beneath is its own gallery Series (credited to
the artist + grouped into a Collection named after them). Move/rename safety comes from
soft-delete + a ``(file_size, partial_hash)`` restore hint. Covers are generated lazily
on first request, so no thumbnail job is enqueued here.

Deferred (follow-ups): filesystem watcher, embedded ComicInfo/OPF metadata, and
multi-chapter archives. (Extra container formats + content-sniffing are not
planned — CBZ + image directories cover the common cases.)
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import xxhash
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from src.catalog.models import Book, Chapter, Library, Series, SeriesCredit
from src.collections.models import Collection, CollectionSeries
from src.core.exceptions import BadRequestError, LycheeError
from src.core.logging import get_logger
from src.core.persistence.base_model import utc_now
from src.ingest.parser import parse
from src.media.containers import IMAGE_EXTS, is_cover_file, open_container
from src.progress.models import ReadingProgress

logger = get_logger(__name__)

_ARCHIVE_KINDS = {".cbz": "cbz", ".zip": "zip"}  # the reader's supported archive kinds
_HASH_CHUNK = 64 * 1024


@dataclass
class ScanSummary:
    """Counts from one scan pass."""

    series_added: int = 0
    books_added: int = 0
    books_updated: int = 0
    books_removed: int = 0


@dataclass
class Candidate:
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
    digest = xxhash.xxh3_128()  # fast, low-collision content fingerprint
    if path.is_dir():
        images = sorted(
            p
            for p in path.iterdir()
            if p.is_file() and _is_image(p.name) and not is_cover_file(p.name)
        )
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


def _candidate(item: Path, root: Path, series_dir: Path, kind: str) -> Candidate:
    parts = list(item.relative_to(series_dir).parts) or [series_dir.name]
    return Candidate(path=item, rel=str(item.relative_to(root)), kind=kind, segments=parts)


def resolve_books(series_dir: Path, root: Path) -> list[Candidate]:
    """Walk a series folder (hybrid rule): image-only dir → book; archive →
    book; a folder holding archives/sub-folders is a grouping level (recurse)."""
    found: list[Candidate] = []

    def visit(directory: Path) -> None:
        entries = sorted(p for p in directory.iterdir() if not p.name.startswith("."))
        if any(e.is_file() and _is_image(e.name) and not is_cover_file(e.name) for e in entries):
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


def _page_count(candidate: Candidate) -> int | None:
    """Open the container to count pages; None if it can't be read (skip it)."""
    try:
        with open_container(candidate.path, candidate.kind) as container:
            return container.page_count()
    except LycheeError as exc:
        logger.warning("scan_skip_unreadable", path=candidate.rel, error=str(exc))
        return None


def scan_library(
    session: Session,
    library: Library,
    *,
    on_progress: Callable[[int, str], None] | None = None,
) -> ScanSummary:
    """Full scan of one library: reconcile its Series/Book/Chapter rows with disk.

    ``on_progress(percent, label)`` is called after each top-level entry so callers
    can surface live progress (SSE).
    """
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

    gallery = _series_kind(library) == "gallery"
    entries = [p for p in sorted(root.iterdir()) if not p.name.startswith(".")]
    for index, entry in enumerate(entries, start=1):
        if gallery and entry.is_dir():
            _ingest_artist(session, library, entry, root, existing, seen, summary)
        else:
            _ingest_entry(session, library, entry, root, existing, seen, summary, artist=None)
        if on_progress is not None:
            on_progress(round(index / len(entries) * 100), entry.name)

    for path_rel, book in existing.items():
        if path_rel not in seen:
            book.deleted_at = utc_now()
            book.restore_progress_json = _snapshot_progress(session, book)
            # Drop the derived chapters (their progress cascades away); the snapshot above
            # lets a later restore of this moved book re-apply that progress.
            _ = session.execute(delete(Chapter).where(Chapter.book_id == book.id))
            summary.books_removed += 1

    library.last_scan_at = utc_now()
    session.flush()
    return summary


def _ingest_entry(
    session: Session,
    library: Library,
    entry: Path,
    root: Path,
    existing: dict[str, Book],
    seen: set[str],
    summary: ScanSummary,
    *,
    artist: str | None,
) -> None:
    """One series from a top-level (or per-artist) entry: a folder of books, or a loose
    archive. ``artist`` credits a gallery to its artist/model folder (+ Collection)."""
    if entry.is_dir():
        candidates = resolve_books(entry, root)
        if not candidates:
            return
        path_rel, title = str(entry.relative_to(root)), entry.name
    elif entry.is_file() and (kind := _archive_kind(entry.name)):
        candidates = [_candidate(entry, root, entry.parent, kind)]
        path_rel, title = str(entry.relative_to(root).with_suffix("")), entry.stem
    else:
        return
    _ingest_series(
        session,
        library,
        path_rel=path_rel,
        title=title,
        candidates=candidates,
        existing=existing,
        seen=seen,
        summary=summary,
        artist=artist,
    )


def _ingest_artist(
    session: Session,
    library: Library,
    artist_dir: Path,
    root: Path,
    existing: dict[str, Book],
    seen: set[str],
    summary: ScanSummary,
) -> None:
    """A gallery library's top folder is an artist/model: each child folder/archive is its
    own gallery series. If the folder *directly* holds page images it's a single gallery
    with no artist level (so flat gallery libraries keep working)."""
    children = [p for p in sorted(artist_dir.iterdir()) if not p.name.startswith(".")]
    if any(p.is_file() and _is_image(p.name) and not is_cover_file(p.name) for p in children):
        _ingest_entry(session, library, artist_dir, root, existing, seen, summary, artist=None)
        return
    for child in children:
        _ingest_entry(
            session, library, child, root, existing, seen, summary, artist=artist_dir.name
        )


def _ingest_series(
    session: Session,
    library: Library,
    *,
    path_rel: str,
    title: str,
    candidates: list[Candidate],
    existing: dict[str, Book],
    seen: set[str],
    summary: ScanSummary,
    artist: str | None = None,
) -> None:
    kind = _series_kind(library)
    # Match on the folder-derived path (stable identity), not the title — provider
    # metadata may rename the title, and rescans must not then create a duplicate.
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
        summary.series_added += 1

    chapters: list[Chapter] = []
    for candidate in candidates:
        book = _reconcile_book(session, library, series, candidate, existing, seen, summary)
        if book is None:
            continue
        if kind == "gallery":
            series.image_count = book.page_count
        else:
            chapters.append(sync_chapter(session, series, book, candidate, title, kind))

    if chapters:
        order_chapters(chapters)

    if artist:
        _credit_artist(session, series, artist)


def _credit_artist(session: Session, series: Series, artist: str) -> None:
    """Credit a gallery series to its artist/model folder + group it into a Collection
    named after them. Idempotent (deduped), so re-scans don't pile up rows."""
    has_credit = session.scalar(
        select(SeriesCredit.id).where(
            SeriesCredit.series_id == series.id,
            SeriesCredit.name == artist,
            SeriesCredit.role == "artist",
        )
    )
    if has_credit is None:
        session.add(SeriesCredit(series_id=series.id, name=artist, role="artist"))

    collection = session.scalar(select(Collection).where(Collection.name == artist))
    if collection is None:
        collection = Collection(name=artist)
        session.add(collection)
        session.flush()
    member = session.scalar(
        select(CollectionSeries.series_id).where(
            CollectionSeries.collection_id == collection.id,
            CollectionSeries.series_id == series.id,
        )
    )
    if member is None:
        next_pos = session.scalar(
            select(func.max(CollectionSeries.position)).where(
                CollectionSeries.collection_id == collection.id
            )
        )
        session.add(
            CollectionSeries(
                collection_id=collection.id,
                series_id=series.id,
                position=(next_pos or 0) + 1,
            )
        )


def _reconcile_book(
    session: Session,
    library: Library,
    series: Series,
    candidate: Candidate,
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


def _snapshot_progress(session: Session, book: Book) -> list[dict[str, object]] | None:
    """Capture a soft-deleted book's chapters' reading progress (keyed by chapter number)
    before the chapters are deleted, so a restore can re-apply it. None when there's none."""
    rows = session.execute(
        select(Chapter.number, ReadingProgress.current_page, ReadingProgress.completed)
        .join(ReadingProgress, ReadingProgress.chapter_id == Chapter.id)
        .where(Chapter.book_id == book.id)
    ).all()
    snapshot: list[dict[str, object]] = [
        {"number": number, "current_page": current_page, "completed": completed}
        for number, current_page, completed in rows
    ]
    return snapshot or None


def _restore_progress(session: Session, series: Series, book: Book, chapter: Chapter) -> None:
    """Re-apply a snapshotted reading position (from a soft-delete) to a chapter recreated
    on restore, matched by number. Consumes the entry and clears the snapshot when empty."""
    snapshot = book.restore_progress_json
    if not snapshot:
        return
    entry = next((row for row in snapshot if row.get("number") == chapter.number), None)
    if entry is None:
        return
    has_progress = session.scalar(
        select(ReadingProgress.id).where(ReadingProgress.chapter_id == chapter.id)
    )
    if has_progress is None:
        page = entry.get("current_page")
        session.add(
            ReadingProgress(
                chapter_id=chapter.id,
                series_id=series.id,
                current_page=page if isinstance(page, int) else 0,
                completed=bool(entry.get("completed")),
            )
        )
    remaining = [row for row in snapshot if row is not entry]
    book.restore_progress_json = remaining or None


def sync_chapter(
    session: Session, series: Series, book: Book, candidate: Candidate, title: str, kind: str
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
    _restore_progress(session, series, book, chapter)
    return chapter


def order_chapters(chapters: list[Chapter]) -> None:
    """Assign a number_sort to chapters that lacked one (base-less specials, volume
    -only books), placing them after their sorted neighbours."""
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
