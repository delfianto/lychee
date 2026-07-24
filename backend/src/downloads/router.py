"""Downloads API (Settings → Downloads)."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from src.core.persistence.database import DbSession
from src.downloads import service
from src.downloads.deps import StorageRootDep
from src.downloads.schema import DownloadCreate, DownloadTaskOut

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


@router.get("")
def list_downloads(db: DbSession) -> list[DownloadTaskOut]:
    return service.list_downloads(db)


@router.post("")
def create_downloads(
    db: DbSession, storage: StorageRootDep, data: DownloadCreate
) -> list[DownloadTaskOut]:
    """Download a series' new chapters from its linked provider."""
    return service.create_downloads(db, data.series_id, storage)


@router.post("/clear-completed", status_code=status.HTTP_204_NO_CONTENT)
def clear_completed(db: DbSession) -> Response:
    service.clear_completed(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{task_id}/retry")
def retry_download(
    db: DbSession, storage: StorageRootDep, task_id: str
) -> list[DownloadTaskOut]:
    return service.retry_download(db, task_id, storage)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_download(db: DbSession, task_id: str) -> Response:
    service.delete_download(db, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
