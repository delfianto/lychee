"""Catalog API — the series grid and series detail."""

from __future__ import annotations

from fastapi import APIRouter, Query

from src.catalog import service
from src.catalog.schema import SeriesOut
from src.core.persistence.database import DbSession
from src.core.schema import Page

router = APIRouter(prefix="/api", tags=["catalog"])


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
