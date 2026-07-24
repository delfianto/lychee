"""Collections (Lists) API."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from src.collections import service
from src.collections.schema import (
    CollectionCreate,
    CollectionDetailOut,
    CollectionOut,
    CollectionSeriesAdd,
    CollectionUpdate,
)
from src.core.persistence.database import DbSession

router = APIRouter(prefix="/api/collections", tags=["collections"])


@router.get("")
def list_collections(db: DbSession) -> list[CollectionOut]:
    return service.list_collections(db)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_collection(db: DbSession, data: CollectionCreate) -> CollectionOut:
    return service.create_collection(db, data)


@router.get("/{collection_id}")
def get_collection(db: DbSession, collection_id: str) -> CollectionDetailOut:
    return service.get_collection(db, collection_id)


@router.patch("/{collection_id}")
def update_collection(db: DbSession, collection_id: str, data: CollectionUpdate) -> CollectionOut:
    return service.update_collection(db, collection_id, data)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(db: DbSession, collection_id: str) -> Response:
    service.delete_collection(db, collection_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{collection_id}/series")
def add_series(db: DbSession, collection_id: str, data: CollectionSeriesAdd) -> CollectionOut:
    return service.add_series(db, collection_id, data.series_id)


@router.delete("/{collection_id}/series/{series_id}")
def remove_series(db: DbSession, collection_id: str, series_id: str) -> CollectionOut:
    return service.remove_series(db, collection_id, series_id)
