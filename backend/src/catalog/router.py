"""Catalog API — the series grid and series detail."""

from __future__ import annotations

from fastapi import APIRouter, Query, Request, Response

from src.catalog import media, service
from src.catalog.deps import ThumbnailStoreDep
from src.catalog.media import Served
from src.catalog.schema import (
    ChapterDetailOut,
    DashboardOut,
    LibrarySummaryOut,
    RecentUpdateOut,
    SeriesArtOut,
    SeriesOut,
    SeriesUpdate,
    VolumeGroupOut,
)
from src.core.persistence.database import DbSession
from src.core.schema import Page

router = APIRouter(prefix="/api", tags=["catalog"])

_IMAGE_CACHE_CONTROL = "public, max-age=86400"


def _image_response(request: Request, served: Served) -> Response:
    """Serve image bytes with an ETag, answering 304 on a matching If-None-Match."""
    if request.headers.get("if-none-match") == served.etag:
        return Response(status_code=304, headers={"ETag": served.etag})
    return Response(
        content=served.data,
        media_type=served.media_type,
        headers={"ETag": served.etag, "Cache-Control": _IMAGE_CACHE_CONTROL},
    )


@router.get("/series")
def list_series(
    db: DbSession,
    kind: str | None = None,
    shelf: str | None = None,
    favorite: bool | None = None,
    q: str | None = None,
    tags: str | None = None,
    tag_mode: str = Query("and", alias="tagMode"),
    ratings: str | None = None,
    demographics: str | None = None,
    pub_status: str | None = Query(None, alias="pubStatus"),
    read_state: str | None = Query(None, alias="readState"),
    artist: str | None = None,
    source: str | None = None,
    sort: str = "recentlyAdded",
    cursor: str | None = None,
    limit: int = 24,
) -> Page[SeriesOut]:
    """The one list endpoint behind every grid (library, favorites, gallery, …)."""
    filters = service.build_series_filters(
        kind=kind,
        shelf=shelf,
        favorite=favorite,
        q=q,
        tags=tags,
        tag_mode=tag_mode,
        ratings=ratings,
        demographics=demographics,
        pub_status=pub_status,
        read_state=read_state,
        artist=artist,
        source=source,
        sort=sort,
    )
    return service.list_series(db, filters=filters, cursor=cursor, limit=limit)


@router.get("/series/{series_id}")
def get_series(db: DbSession, series_id: str) -> SeriesOut:
    """Full series detail."""
    return service.get_series(db, series_id)


@router.patch("/series/{series_id}")
def update_series(db: DbSession, series_id: str, data: SeriesUpdate) -> SeriesOut:
    """Persist detail action-row edits: favorite / library status / personal rating."""
    return service.update_series(db, series_id, data)


@router.get("/series/{series_id}/chapters")
def list_chapters(
    db: DbSession, series_id: str, language: str | None = None, order: str = "desc"
) -> list[VolumeGroupOut]:
    """Chapters grouped by volume (Related/chapters tab)."""
    return service.list_chapters(db, series_id, language=language, order=order)


@router.get("/chapters/{chapter_id}")
def get_chapter(db: DbSession, chapter_id: str) -> ChapterDetailOut:
    """Chapter detail for the reader."""
    return service.get_chapter(db, chapter_id)


@router.get("/updates")
def updates(db: DbSession, cursor: str | None = None, limit: int = 24) -> Page[RecentUpdateOut]:
    """Recently updated chapters across the library."""
    return service.updates(db, unread_only=False, cursor=cursor, limit=limit)


@router.get("/updates/unread")
def unread_updates(
    db: DbSession, cursor: str | None = None, limit: int = 24
) -> Page[RecentUpdateOut]:
    """Unread chapters across the library."""
    return service.updates(db, unread_only=True, cursor=cursor, limit=limit)


@router.get("/dashboard")
def dashboard(db: DbSession) -> DashboardOut:
    """One call for the Home dashboard: stats + continue-reading + updates + added."""
    return service.dashboard(db)


@router.get("/libraries/summary")
def libraries_summary(db: DbSession) -> list[LibrarySummaryOut]:
    """Per-library storage usage (Home strip + About)."""
    return service.library_summaries(db)


@router.get("/search")
def search(db: DbSession, q: str = "", limit: int = 20) -> list[SeriesOut]:
    """Title search powering the navbar."""
    return service.search(db, q, limit=limit)


@router.get("/series/{series_id}/related")
def related(db: DbSession, series_id: str) -> list[SeriesOut]:
    """Other series of the same kind (Related tab)."""
    return service.related(db, series_id)


@router.get("/series/{series_id}/art")
def series_art(db: DbSession, series_id: str) -> SeriesArtOut:
    """Extra art for a series (Art tab)."""
    return service.series_art(db, series_id)


@router.get("/series/{series_id}/images")
def gallery_images(
    db: DbSession, series_id: str, cursor: str | None = None, limit: int = 24
) -> Page[str]:
    """Cursor-paginated gallery image URLs (GalleryDetail grid + Lightbox)."""
    return media.gallery_images(db, series_id, cursor=cursor, limit=limit)


@router.get("/series/{series_id}/cover")
def series_cover(
    request: Request, db: DbSession, store: ThumbnailStoreDep, series_id: str, size: str = "cover"
) -> Response:
    """AVIF cover thumbnail (size = cover | detail)."""
    return _image_response(request, media.get_cover(db, store, series_id, size))


@router.get("/series/{series_id}/images/{index}")
def gallery_image(request: Request, db: DbSession, series_id: str, index: int) -> Response:
    """A single gallery image (AVIF or original bytes)."""
    return _image_response(request, media.get_gallery_image(db, series_id, index))


@router.get("/chapters/{chapter_id}/pages/{n}")
def chapter_page(request: Request, db: DbSession, chapter_id: str, n: int) -> Response:
    """A single chapter page (1-based); ETag + Cache-Control + 304."""
    return _image_response(request, media.get_page(db, chapter_id, n))
