"""Binary media serving: covers, chapter pages, and gallery images.

Covers are AVIF thumbnails: served from the store, and lazily generated from the
first page of the series' first book on a miss. Pages and gallery images are read
straight from their book container (downloaded content is already AVIF; scanned
originals are served as-is). Every response carries a content-hash ETag.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.models import Book, Chapter, Library, Series
from src.core.exceptions import LycheeError, NotFoundError
from src.core.logging import get_logger
from src.core.schema import Page, decode_cursor, encode_cursor
from src.media.containers import open_container
from src.media.render_cache import RenderCache, render_width
from src.media.thumbnails import ThumbnailStore, ThumbVariant

logger = get_logger(__name__)

# Downloading a provider cover once (then serving it as a local AVIF thumbnail),
# rather than hotlinking. A non-spoofed UA keeps MangaDex's CDN happy.
_COVER_UA = "lychee/0.0.1 (self-hosted manga server)"

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


def _download_image(url: str) -> bytes | None:
    """Best-effort download of a remote image (a provider cover). None on any failure."""
    try:
        response = httpx.get(
            url, headers={"User-Agent": _COVER_UA}, timeout=15.0, follow_redirects=True
        )
        if response.status_code == 200:
            return response.content
    except httpx.HTTPError as exc:
        logger.warning("cover_download_failed", url=url, error=str(exc))
    return None


def _cover_source_bytes(session: Session, series_id: str) -> bytes | None:
    """The best cover image bytes for a series: the provider cover (downloaded once) if
    set, else the first book's first page. None when neither is available/readable."""
    series = session.get(Series, series_id)
    if series is None:
        return None
    if series.cover_source and series.cover_source.startswith("http"):
        remote = _download_image(series.cover_source)
        if remote is not None:
            return remote
    book = _first_book(session, series_id)
    if book is None:
        return None
    try:
        data, _ = _read_page(session, book, 0)
    except LycheeError:
        return None
    return data


def generate_series_cover(
    session: Session, store: ThumbnailStore, series_id: str, *, overwrite: bool = False
) -> bool:
    """Generate a series' cover thumbnails — the provider cover if the series has one
    (downloaded + cached locally, never hotlinked), else its first book's first page.

    Idempotent and best-effort: skips when every variant already exists (unless
    ``overwrite``), no-ops when there's no cover source, and swallows failures. Returns
    whether it generated. Used to warm covers eagerly on download/scan.
    """
    if not overwrite and all(store.exists(series_id, variant) for variant in ThumbVariant):
        return False
    source = _cover_source_bytes(session, series_id)
    if source is None:
        return False
    try:
        store.generate_all(series_id, source, overwrite=overwrite)
    except Exception as exc:  # noqa: BLE001 - warming must never break the download/scan
        logger.warning("cover_generate_failed", series_id=series_id, error=str(exc))
        return False
    return True


def get_cover(session: Session, store: ThumbnailStore, series_id: str, size: str) -> Served:
    """Serve a series cover thumbnail (cached AVIF), generating it on a miss from the
    provider cover or the first page."""
    variant = ThumbVariant.DETAIL if size == "detail" else ThumbVariant.COVER
    data = store.read(series_id, variant)
    if data is None:
        if session.get(Series, series_id) is None:
            raise NotFoundError(f"series {series_id!r} not found")
        _ = generate_series_cover(session, store, series_id)
        data = store.read(series_id, variant)
        if data is None:
            raise NotFoundError("no cover source for series")
    return Served(data=data, media_type="image/avif", etag=_etag(data))


def warm_library_covers(session: Session, store: ThumbnailStore, library_id: str) -> int:
    """Warm covers for every series in a library (best-effort). Returns the count generated."""
    warmed = 0
    for series_id in session.scalars(select(Series.id).where(Series.library_id == library_id)):
        if generate_series_cover(session, store, series_id):
            warmed += 1
    return warmed


def get_page(
    session: Session,
    chapter_id: str,
    n: int,
    *,
    width: int | None = None,
    render_cache: RenderCache | None = None,
) -> Served:
    """Serve page ``n`` (1-based) of a chapter. With ``width`` + a ``render_cache``, serve
    an AVIF re-encoded to at most that width (cached on disk); otherwise the raw page."""
    chapter = session.get(Chapter, chapter_id)
    if chapter is None:
        raise NotFoundError(f"chapter {chapter_id!r} not found")
    if not 1 <= n <= chapter.page_count:
        raise NotFoundError(f"page {n} out of range (1–{chapter.page_count})")
    book = session.get(Book, chapter.book_id)
    if book is None:
        raise NotFoundError("book missing for chapter")
    index = chapter.page_start + n - 1

    if width is not None and render_cache is not None:
        cached = render_cache.get(book.id, index, width)
        if cached is not None:
            return Served(data=cached, media_type="image/avif", etag=_etag(cached))
        raw, _ = _read_page(session, book, index)
        rendered = render_width(raw, width)
        render_cache.put(book.id, index, width, rendered)
        return Served(data=rendered, media_type="image/avif", etag=_etag(rendered))

    data, name = _read_page(session, book, index)
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
