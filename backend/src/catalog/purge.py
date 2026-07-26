"""Remove local chapter/book content from disk (and optionally from the DB).

Provider-managed chapters (downloaded from MangaDex etc.) keep the series + remote
index so the chapter can be re-downloaded; local scanned chapters are purged entirely.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.catalog.models import Book, Chapter, Library, Series
from src.catalog.schema import DeleteChapterOut
from src.core.exceptions import BadRequestError, NotFoundError
from src.core.logging import get_logger
from src.core.persistence.base_model import utc_now

logger = get_logger(__name__)


def is_provider_managed(chapter: Chapter) -> bool:
    """True when this chapter was downloaded from a remote provider (re-downloadable)."""
    return bool(chapter.provider_chapter_id or chapter.provider)


def _resolve_book_path(library: Library, book: Book) -> Path | None:
    """Absolute path for the book, or None if the library root is virtual/unusable."""
    root = library.path or ""
    if root.startswith(("mangadex://", "http://", "https://")):
        return None
    base = Path(root).resolve()
    target = (base / book.path_rel).resolve()
    # Path-traversal guard: must stay under the library root.
    try:
        _ = target.relative_to(base)
    except ValueError as exc:
        raise BadRequestError("book path escapes library root") from exc
    return target


def _delete_path(path: Path, *, content_kind: str) -> None:
    """Best-effort remove a file or directory; missing paths are fine."""
    try:
        if not path.exists():
            return
        if content_kind in {"image_dir", "avif_dir"} or path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
    except OSError as exc:
        logger.warning("purge_path_failed", path=str(path), error=str(exc))


def _recompute_available(session: Session, series: Series) -> None:
    """Refresh available_chapters from remote index vs remaining local numbers."""
    from src.catalog.models import ProviderChapter

    remote_nums = set(
        session.scalars(
            select(ProviderChapter.number).where(
                ProviderChapter.series_id == series.id, ProviderChapter.number.is_not(None)
            )
        )
    )
    if not remote_nums:
        return
    local_nums = set(session.scalars(select(Chapter.number).where(Chapter.series_id == series.id)))
    series.available_chapters = sum(1 for n in remote_nums if n not in local_nums)


def delete_chapter_local(session: Session, chapter_id: str) -> DeleteChapterOut:
    """Delete a chapter's local files and clean the DB (provider-aware)."""
    chapter = session.get(Chapter, chapter_id)
    if chapter is None:
        raise NotFoundError(f"chapter {chapter_id!r} not found")

    book = session.get(Book, chapter.book_id)
    if book is None:
        raise NotFoundError(f"book for chapter {chapter_id!r} not found")
    if book.deleted_at is not None:
        raise NotFoundError(f"chapter {chapter_id!r} already removed")

    series = session.get(Series, chapter.series_id)
    if series is None:
        raise NotFoundError(f"series for chapter {chapter_id!r} not found")

    library = session.get(Library, book.library_id)
    if library is None:
        raise NotFoundError("library missing for book")

    path = _resolve_book_path(library, book)
    if path is not None:
        _delete_path(path, content_kind=book.content_kind)

    provider_managed = is_provider_managed(chapter)
    # Remove all chapters on this book (today downloads are 1:1 book↔chapter).
    chapter_ids = list(session.scalars(select(Chapter.id).where(Chapter.book_id == book.id)))
    _ = session.execute(delete(Chapter).where(Chapter.book_id == book.id))

    if provider_managed:
        book.deleted_at = utc_now()
        book.page_count = 0
        book.file_size = 0
        mode = "provider"
        redownloadable = True
    else:
        session.delete(book)
        mode = "local"
        redownloadable = False

    _recompute_available(session, series)
    session.commit()
    logger.info(
        "chapter_purged",
        chapter_id=chapter_id,
        book_id=book.id,
        mode=mode,
        path=str(path) if path else None,
        chapters=len(chapter_ids),
    )
    return DeleteChapterOut(mode=mode, redownloadable=redownloadable, series_id=series.id)
