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
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.models import Book, Chapter, Library, Series
from src.catalog.schema import GalleryMediaItem
from src.core.exceptions import BadRequestError, LycheeError, NotFoundError
from src.core.logging import get_logger
from src.core.schema import Page, decode_cursor, encode_cursor
from src.media.avif import ContentClass, encode, load_image
from src.media.containers import ImageDirContainer, is_cover_file, media_kind, open_container
from src.media.render_cache import RenderCache, render_width
from src.media.thumbnails import ThumbnailStore, ThumbVariant
from src.media.video import extract_poster_png

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
    ".mp4": "video/mp4",
    ".m4v": "video/mp4",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
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


def _local_cover_page_bytes(session: Session, series_id: str) -> bytes | None:
    """First readable still/GIF page of the series' first book (skips video pages)."""
    book = _first_book(session, series_id)
    if book is None:
        return None
    library = session.get(Library, book.library_id)
    if library is None:
        return None
    root = Path(library.path) / book.path_rel
    try:
        with open_container(root, book.content_kind) as container:
            for index in range(container.page_count()):
                name = container.page_name(index)
                if media_kind(name) == "video":
                    continue  # don't feed MP4 bytes into Pillow
                try:
                    return container.read_page(index)
                except LycheeError:
                    continue
    except LycheeError:
        return None
    return None


def _raw_cover_source(session: Session, series_id: str) -> bytes | None:
    """Raw bytes to *build* a cover from.

    Order:
    1. On-disk local page for **gallery** series (never prefer a remote manga cover).
    2. Provider HTTP ``cover_source`` for manga/comic (downloaded once).
    3. First local still page of the first book.

    None when nothing is available/readable.
    """
    series = session.get(Series, series_id)
    if series is None:
        return None

    # Galleries are folder art — local media is the cover, not a MangaDex match.
    if series.kind == "gallery":
        return _local_cover_page_bytes(session, series_id)

    if series.cover_source and series.cover_source.startswith("http"):
        remote = _download_image(series.cover_source)
        if remote is not None:
            return remote
    return _local_cover_page_bytes(session, series_id)


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


@dataclass(slots=True)
class GalleryFile:
    """Resolved on-disk gallery media for streaming or byte serve."""

    path: Path
    name: str
    kind: str  # image | gif | video
    media_type: str


def _gallery_book(session: Session, series_id: str) -> Book:
    book = _first_book(session, series_id)
    if book is None:
        raise NotFoundError("no images for series")
    return book


def resolve_gallery_file(session: Session, series_id: str, index: int) -> GalleryFile:
    """Absolute path + kind for gallery item ``index`` (0-based).

    Video streaming requires a real on-disk path (directory containers only).
    """
    book = _gallery_book(session, series_id)
    if not 0 <= index < book.page_count:
        raise NotFoundError(f"image {index} out of range (0–{book.page_count - 1})")
    library = session.get(Library, book.library_id)
    if library is None:
        raise NotFoundError("library missing for book")
    root = Path(library.path) / book.path_rel
    with open_container(root, book.content_kind) as container:
        name = container.page_name(index)
        kind = media_kind(name)
        if isinstance(container, ImageDirContainer):
            path = container.page_path(index)
        elif kind == "video":
            raise BadRequestError("video in archives is not supported")
        else:
            path = root  # unused for stills (bytes come from read_page)
    return GalleryFile(path=path, name=name, kind=kind, media_type=_mime(name))


def get_gallery_image(session: Session, series_id: str, index: int) -> Served:
    """Serve still/GIF bytes for gallery item ``index`` (not video — use FileResponse)."""
    info = resolve_gallery_file(session, series_id, index)
    if info.kind == "video":
        raise BadRequestError("use the video stream path for MP4 items")
    book = _gallery_book(session, series_id)
    data, name = _read_page(session, book, index)
    return Served(data=data, media_type=_mime(name), etag=_etag(data))


def _gallery_item_thumb_id(series_id: str, index: int) -> str:
    """Stable ThumbnailStore id for one gallery media item (grid preview).

    ``series_id`` leads so the store's ``id[:2]`` sharding spreads gallery items
    across shards by series (a fixed literal prefix like ``gi-`` would put every
    gallery item in the library under one shard directory).
    """
    return f"{series_id}-gi-{index}"


def ensure_gallery_item_thumb(
    session: Session, store: ThumbnailStore, series_id: str, index: int, *, overwrite: bool = False
) -> bool:
    """Generate the grid AVIF for one gallery item if missing. Returns whether it wrote."""
    thumb_id = _gallery_item_thumb_id(series_id, index)
    if not overwrite and store.exists(thumb_id, ThumbVariant.COVER):
        return False
    info = resolve_gallery_file(session, series_id, index)
    try:
        if info.kind == "video":
            png = extract_poster_png(info.path)
            if png is None:
                return False
            store.generate(
                thumb_id,
                png,
                ThumbVariant.COVER,
                content_class=ContentClass.PHOTO,
                overwrite=overwrite,
            )
        else:
            book = _gallery_book(session, series_id)
            data, _ = _read_page(session, book, index)
            store.generate(
                thumb_id,
                data,
                ThumbVariant.COVER,
                content_class=ContentClass.PHOTO,
                overwrite=overwrite,
            )
    except Exception as exc:  # noqa: BLE001 - best-effort warm / on-demand
        logger.warning("gallery_thumb_failed", series_id=series_id, index=index, error=str(exc))
        return False
    return True


def get_gallery_thumb(
    session: Session, store: ThumbnailStore, series_id: str, index: int
) -> Served:
    """Small grid preview (AVIF ~320px). Lazy-generates on miss so unscanned items shimmer once."""
    thumb_id = _gallery_item_thumb_id(series_id, index)
    cached = store.read(thumb_id, ThumbVariant.COVER)
    if cached is None:
        _ = ensure_gallery_item_thumb(session, store, series_id, index)
        cached = store.read(thumb_id, ThumbVariant.COVER)
        if cached is None:
            raise NotFoundError("could not build gallery thumbnail")
    return Served(data=cached, media_type="image/avif", etag=_etag(cached))


def get_gallery_poster(
    session: Session, store: ThumbnailStore, series_id: str, index: int
) -> Served:
    """Video poster — same store entry as the grid thumb (ffmpeg frame → AVIF)."""
    info = resolve_gallery_file(session, series_id, index)
    if info.kind != "video":
        raise BadRequestError("poster is only available for video items")
    return get_gallery_thumb(session, store, series_id, index)


def warm_gallery_item_thumbs(
    session: Session,
    store: ThumbnailStore,
    library_id: str,
    *,
    on_progress: Callable[[int, str], None] | None = None,
) -> int:
    """Pre-generate grid thumbs for every still/GIF/video in a gallery library.

    Called after scan so the detail grid does not hit full-resolution originals.
    Idempotent; skips ids that already exist.
    """
    series_ids = list(
        session.scalars(
            select(Series.id).where(Series.library_id == library_id, Series.kind == "gallery")
        )
    )
    if not series_ids:
        return 0
    warmed = 0
    total = len(series_ids)
    for n, series_id in enumerate(series_ids, start=1):
        book = _first_book(session, series_id)
        if book is None or book.page_count <= 0:
            if on_progress is not None:
                on_progress(round(n / total * 100), f"Series {n}/{total}")
            continue
        for index in range(book.page_count):
            if ensure_gallery_item_thumb(session, store, series_id, index):
                warmed += 1
        if on_progress is not None:
            # Honest 0–100 across series so ActivityIndicator moves during encodes.
            on_progress(round(n / total * 100), f"Thumbs {n}/{total} series · {warmed} new")
    return warmed


def gallery_images(
    session: Session, series_id: str, *, cursor: str | None, limit: int
) -> Page[GalleryMediaItem]:
    """Cursor-paginated gallery media items (kind + urls for grid/lightbox)."""
    if session.get(Series, series_id) is None:
        raise NotFoundError(f"series {series_id!r} not found")
    book = _first_book(session, series_id)
    total = book.page_count if book is not None else 0
    offset = int(decode_cursor(cursor)["o"]) if cursor is not None else 0
    end = min(offset + limit, total)

    items: list[GalleryMediaItem] = []
    if book is not None and offset < end:
        library = session.get(Library, book.library_id)
        if library is None:
            raise NotFoundError("library missing for book")
        root = Path(library.path) / book.path_rel
        with open_container(root, book.content_kind) as container:
            for i in range(offset, end):
                name = container.page_name(i)
                kind = media_kind(name)
                url = f"/api/series/{series_id}/images/{i}"
                # Grid always uses /thumb (lazy-generated AVIF). Video lightbox uses url stream.
                thumb = f"{url}/thumb"
                poster = f"{url}/poster" if kind == "video" else None
                items.append(
                    GalleryMediaItem(
                        index=i, kind=kind, url=url, thumb_url=thumb, poster_url=poster
                    )
                )

    next_cursor = encode_cursor({"o": end}) if end < total else None
    return Page[GalleryMediaItem](items=items, next_cursor=next_cursor)
