"""Library API — CRUD + scan triggers."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from src.core.persistence.database import DbSession
from src.downloads.deps import StorageRootDep
from src.library import service
from src.library.schema import LibraryCreate, LibraryOut, LibraryUpdate
from src.tasks.schema import TaskOut

router = APIRouter(prefix="/api/libraries", tags=["libraries"])


@router.get("")
def list_libraries(db: DbSession) -> list[LibraryOut]:
    return service.list_libraries(db)


@router.post("", status_code=status.HTTP_201_CREATED)
def create_library(db: DbSession, data: LibraryCreate) -> LibraryOut:
    return service.create_library(db, data)


@router.post("/scan", status_code=status.HTTP_202_ACCEPTED)
def scan_all(db: DbSession, storage: StorageRootDep) -> TaskOut:
    """Scan every enabled library in the background; returns the task to follow via SSE."""
    return service.enqueue_scan_all(db, storage)


@router.patch("/{library_id}")
def update_library(db: DbSession, library_id: str, data: LibraryUpdate) -> LibraryOut:
    return service.update_library(db, library_id, data)


@router.delete("/{library_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_library(db: DbSession, library_id: str) -> Response:
    service.delete_library(db, library_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{library_id}/scan", status_code=status.HTTP_202_ACCEPTED)
def scan_library(db: DbSession, storage: StorageRootDep, library_id: str) -> TaskOut:
    """Scan one library in the background; returns the task to follow via /api/events."""
    return service.enqueue_scan_one(db, library_id, storage)
