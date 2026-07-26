"""Binary media serving: covers, chapter pages, and gallery images.

Covers are AVIF: a series' canonical cover is a ``Cover.avif`` file beside its books
(written for managed libraries; a ``cover.*``/``folder.*`` convention read for scanned
ones), falling back to the provider cover or the first page. The hero (``?size=detail``)
serves that canonical image; grids serve a 320px thumbnail derived into the store. Pages
and gallery images are read straight from their book container. Every response carries a
content-hash ETag.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.models import Book, Chapter, Library, Series
from src.core.exceptions import LycheeError, NotFoundError
from src.core.logging import get_logger
from src.core.schema import Page, decode_cursor, encode_cursor
from src.media.avif import ContentClass, encode, load_image
from src.media.containers import is_cover_file, open_container
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
        select(Book).where(Book.series_id == series_id).order_by(Book.created_at, Book.id).limit(1)
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


def _raw_cover_source(session: Session, series_id: str) -> bytes | None:
    """Raw bytes to *build* a cover from: the provider cover (downloaded once) if set,
    else the series' first book's first page. None when neither is available/readable."""
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


# The canonical cover: a `Cover.avif` beside a series' books (written for managed
# libraries; a `cover.*`/`folder.*` convention read for scanned ones).
_COVER_MAX_EDGE = 640
_COVER_FILE = "Cover.avif"


def _series_dir(session: Session, series: Series) -> Path | None:
    """The on-disk directory holding a series' books + its ``Cover.avif``: the scanned
    series folder (``<library>/<path_rel>``) or the managed ``<library>/<series_id>`` dir.
    None for a loose one-shot (a bare archive with no folder of its own)."""
    library = session.get(Library, series.library_id)
    if library is None:
        return None
    root = Path(library.path)
    if series.path_rel:
        folder = root / series.path_rel
        if folder.is_dir():
            return folder
    managed = root / series.id
    return managed if managed.is_dir() else None


def _on_disk_cover(series_dir: Path) -> Path | None:
    """A cover file in ``series_dir`` — ``Cover.avif`` first, else a ``cover.*``/``folder.*``
    image (case-insensitive)."""
    preferred = series_dir / _COVER_FILE
    if preferred.is_file():
        return preferred
    return next(
        (p for p in sorted(series_dir.iterdir()) if p.is_file() and is_cover_file(p.name)),
        None,
    )


def _normalize_cover_avif(data: bytes) -> bytes:
    """Resize (longest edge ≤ 640, never upscaling) + AVIF-encode arbitrary image bytes."""
    image = load_image(data)
    image.thumbnail((_COVER_MAX_EDGE, _COVER_MAX_EDGE))
    return encode(image, content_class=ContentClass.COLOR_ART)


def _canonical_cover_bytes(session: Session, series_id: str) -> bytes | None:
    """The canonical hero cover (AVIF): the on-disk ``Cover.avif``/``cover.*``/``folder.*``
    if present (normalized when not already AVIF), else the raw source normalized. None
    when there's no cover source at all. Read-only — never writes."""
    series = session.get(Series, series_id)
    if series is None:
        return None
    directory = _series_dir(session, series)
    if directory is not None:
        cover = _on_disk_cover(directory)
        if cover is not None:
            data = cover.read_bytes()
            return data if cover.suffix.lower() == ".avif" else _normalize_cover_avif(data)
    raw = _raw_cover_source(session, series_id)
    return _normalize_cover_avif(raw) if raw is not None else None


def write_series_cover(session: Session, series_id: str, series_dir: Path) -> bool:
    """Write ``<series_dir>/Cover.avif`` (normalized AVIF of the raw source) so a managed
    series' cover is a portable file beside its books. Best-effort (swallows failures);
    returns whether it wrote."""
    raw = _raw_cover_source(session, series_id)
    if raw is None:
        return False
    try:
        _write_bytes_atomic(series_dir / _COVER_FILE, _normalize_cover_avif(raw))
    except Exception as exc:  # noqa: BLE001 - cover writing must never break import/download
        logger.warning("cover_write_failed", series_id=series_id, error=str(exc))
        return False
    return True


def _write_bytes_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp")
    _ = tmp.write_bytes(data)
    os.replace(tmp, path)


def generate_series_cover(
    session: Session, store: ThumbnailStore, series_id: str, *, overwrite: bool = False
) -> bool:
    """Generate a series' derived 320px grid thumbnail from its canonical cover (the
    on-disk ``Cover.avif``/``cover.*``/``folder.*``, else the provider cover / first page).

    Idempotent + best-effort: skips when the thumbnail exists (unless ``overwrite``),
    no-ops with no cover source, swallows failures. Returns whether it generated.
    """
    if not overwrite and store.exists(series_id, ThumbVariant.COVER):
        return False
    source = _canonical_cover_bytes(session, series_id)
    if source is None:
        return False
    try:
        store.generate(series_id, source, ThumbVariant.COVER, overwrite=overwrite)
    except Exception as exc:  # noqa: BLE001 - warming must never break the download/scan
        logger.warning("cover_generate_failed", series_id=series_id, error=str(exc))
        return False
    return True


def materialize_series_cover(
    session: Session, store: ThumbnailStore, series_id: str, *, overwrite: bool = False
) -> bool:
    """Download/resolve the cover source once and write both thumbnail variants (cover +
    detail) into the store. Idempotent: no-ops when both variants exist unless
    ``overwrite``. Best-effort — swallows failures so metadata/sync never aborts.
    """
    if (
        not overwrite
        and store.exists(series_id, ThumbVariant.COVER)
        and store.exists(series_id, ThumbVariant.DETAIL)
    ):
        return False
    # Prefer raw bytes so generate_all can size both variants from one decode,
    # rather than re-encoding an already-downscaled AVIF for the grid size.
    raw = _raw_cover_source(session, series_id)
    if raw is None:
        source = _canonical_cover_bytes(session, series_id)
        if source is None:
            return False
        raw = source
    try:
        store.generate_all(series_id, raw, overwrite=overwrite)
    except Exception as exc:  # noqa: BLE001 - cover warm must never break callers
        logger.warning("cover_materialize_failed", series_id=series_id, error=str(exc))
        return False
    return True


def get_cover(session: Session, store: ThumbnailStore, series_id: str, size: str) -> Served:
    """Serve a series cover from the thumbnail store (``cover`` ~320px, ``detail`` ~640px).

    On a store miss, materializes both variants from the canonical/provider source so
    subsequent requests (including detail for virtual MangaDex series with no series dir)
    never re-hit the remote CDN.
    """
    if session.get(Series, series_id) is None:
        raise NotFoundError(f"series {series_id!r} not found")
    variant = ThumbVariant.DETAIL if size == "detail" else ThumbVariant.COVER
    data = store.read(series_id, variant)
    if data is None:
        _ = materialize_series_cover(session, store, series_id)
        data = store.read(series_id, variant)
        if data is None:
            raise NotFoundError("no cover source for series")
    return Served(data=data, media_type="image/avif", etag=_etag(data))


def warm_library_covers(session: Session, store: ThumbnailStore, library_id: str) -> int:
    """Warm cover + detail thumbnails for every series in a library (best-effort)."""
    warmed = 0
    for series_id in session.scalars(select(Series.id).where(Series.library_id == library_id)):
        if materialize_series_cover(session, store, series_id):
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
