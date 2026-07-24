"""Binary media serving: covers, chapter pages, and gallery images (ADR 09 / 19).

Covers are AVIF thumbnails: served from the store, and lazily generated from the
first page of the series' first book on a miss. Pages and gallery images are read
straight from their book container (downloaded content is already AVIF; scanned
originals are served as-is per ADR 09). Every response carries a content-hash ETag.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.models import Book, Chapter, Library, Series
from src.core.exceptions import NotFoundError
from src.core.schema import Page, decode_cursor, encode_cursor
from src.media.containers import open_container
from src.media.thumbnails import ThumbnailStore, ThumbVariant

_MIME = {
    ".avif": "image/avif",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
}


@dataclass(slots=True)
class Served:
    """A binary payload ready to serve, with its content-hash ETag."""

    data: bytes
    media_type: str
    etag: str


def _mime(name: str) -> str:
    return _MIME.get(Path(name).suffix.lower(), "application/octet-stream")


def _etag(data: bytes) -> str:
    return f'"{hashlib.sha1(data).hexdigest()[:16]}"'


def _first_book(session: Session, series_id: str) -> Book | None:
    return session.scalar(
        select(Book)
        .where(Book.series_id == series_id)
        .order_by(Book.created_at, Book.id)
        .limit(1)
    )


def _read_page(session: Session, book: Book, index: int) -> tuple[bytes, str]:
    library = session.get(Library, book.library_id)
    if library is None:
        raise NotFoundError("library missing for book")
    path = Path(library.path) / book.path_rel
    with open_container(path, book.content_kind) as container:
        return container.read_page(index), container.page_name(index)


def get_cover(session: Session, store: ThumbnailStore, series_id: str, size: str) -> Served:
    """Serve a series cover thumbnail, generating it from the first page on a miss."""
    variant = ThumbVariant.DETAIL if size == "detail" else ThumbVariant.COVER
    data = store.read(series_id, variant)
    if data is None:
        if session.get(Series, series_id) is None:
            raise NotFoundError(f"series {series_id!r} not found")
        book = _first_book(session, series_id)
        if book is None:
            raise NotFoundError("no cover source for series")
        source, _ = _read_page(session, book, 0)
        _ = store.generate(series_id, source, variant)
        data = store.read(series_id, variant)
        if data is None:  # pragma: no cover - defensive
            raise NotFoundError("cover generation failed")
    return Served(data=data, media_type="image/avif", etag=_etag(data))


def get_page(session: Session, chapter_id: str, n: int) -> Served:
    """Serve page ``n`` (1-based) of a chapter."""
    chapter = session.get(Chapter, chapter_id)
    if chapter is None:
        raise NotFoundError(f"chapter {chapter_id!r} not found")
    if not 1 <= n <= chapter.page_count:
        raise NotFoundError(f"page {n} out of range (1–{chapter.page_count})")
    book = session.get(Book, chapter.book_id)
    if book is None:
        raise NotFoundError("book missing for chapter")
    data, name = _read_page(session, book, chapter.page_start + n - 1)
    return Served(data=data, media_type=_mime(name), etag=_etag(data))


def get_gallery_image(session: Session, series_id: str, index: int) -> Served:
    """Serve image ``index`` (0-based) of a gallery series."""
    book = _first_book(session, series_id)
    if book is None:
        raise NotFoundError("no images for series")
    if not 0 <= index < book.page_count:
        raise NotFoundError(f"image {index} out of range (0–{book.page_count - 1})")
    data, name = _read_page(session, book, index)
    return Served(data=data, media_type=_mime(name), etag=_etag(data))


def gallery_images(
    session: Session, series_id: str, *, cursor: str | None, limit: int
) -> Page[str]:
    """A cursor-paginated list of gallery image URLs (offset-based cursor)."""
    if session.get(Series, series_id) is None:
        raise NotFoundError(f"series {series_id!r} not found")
    book = _first_book(session, series_id)
    total = book.page_count if book is not None else 0
    offset = int(decode_cursor(cursor)["o"]) if cursor is not None else 0
    end = min(offset + limit, total)
    items = [f"/api/series/{series_id}/images/{i}" for i in range(offset, end)]
    next_cursor = encode_cursor({"o": end}) if end < total else None
    return Page[str](items=items, next_cursor=next_cursor)
