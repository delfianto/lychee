"""Collections (Lists) API."""

from __future__ import annotations

from fastapi import APIRouter, Query, Response, status

from src.collections import mangadex, service
from src.collections.schema import (
    CollectionCreate,
    CollectionDetailOut,
    CollectionOut,
    CollectionSeriesAdd,
    CollectionUpdate,
    ListChapterOut,
    ListFollow,
    ListImport,
    RemoteListOut,
)
from src.core.persistence.database import DbSession
from src.core.schema import OffsetPage
from src.tasks.schema import TaskOut

router = APIRouter(prefix="/api/collections", tags=["collections"])


@router.get("")
def list_collections(db: DbSession) -> list[CollectionOut]:
    return service.list_collections(db)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_collection(db: DbSession, data: CollectionCreate) -> CollectionOut:
    return service.create_collection(db, data)


@router.post("/mangadex/import", status_code=202)
def import_mdlist(data: ListImport) -> TaskOut:
    return mangadex.enqueue_import(data.reference)


@router.post("/mangadex/sync", status_code=202)
def sync_mdlists() -> TaskOut:
    return mangadex.enqueue_account_lists()


@router.get("/mangadex/users/{reference}/lists")
def browse_user_lists(db: DbSession, reference: str) -> list[RemoteListOut]:
    return mangadex.browse_user(db, reference)


@router.post("/{collection_id}/sync", status_code=202)
def sync_mdlist(db: DbSession, collection_id: str) -> TaskOut:
    return mangadex.enqueue_sync(db, collection_id)


@router.put("/{collection_id}/follow")
def follow_mdlist(db: DbSession, collection_id: str, data: ListFollow) -> CollectionOut:
    return service.follow_collection(db, collection_id, data.followed)


@router.get("/{collection_id}/feed")
def list_feed(
    db: DbSession,
    collection_id: str,
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=1, le=100),
    language: str | None = Query(None, pattern=r"^[a-zA-Z-]{2,5}$"),
) -> OffsetPage[ListChapterOut]:
    return service.collection_feed(
        db, collection_id, page=page, page_size=page_size, language=language
    )


@router.get("/{collection_id}")
def get_collection(db: DbSession, collection_id: str) -> CollectionDetailOut:
    return service.get_collection(db, collection_id)


@router.patch("/{collection_id}")
def update_collection(db: DbSession, collection_id: str, data: CollectionUpdate) -> CollectionOut:
    return service.update_collection(db, collection_id, data)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(db: DbSession, collection_id: str, remote: bool = False) -> Response:
    service.delete_collection(db, collection_id, remote=remote)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{collection_id}/series")
def add_series(db: DbSession, collection_id: str, data: CollectionSeriesAdd) -> CollectionOut:
    return service.add_series(db, collection_id, data.series_id)


@router.delete("/{collection_id}/series/{series_id}")
def remove_series(db: DbSession, collection_id: str, series_id: str) -> CollectionOut:
    return service.remove_series(db, collection_id, series_id)
