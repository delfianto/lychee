"""Downloads API (Settings → Downloads)."""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from fastapi.responses import JSONResponse

from src.core.exceptions import BadRequestError
from src.core.persistence.database import DbSession
from src.downloads import service
from src.downloads.deps import StorageRootDep
from src.downloads.schema import DownloadCreate, DownloadTaskOut
from src.tasks.schema import TaskOut

router = APIRouter(prefix="/api/downloads", tags=["downloads"])


@router.get("")
def list_downloads(db: DbSession) -> list[DownloadTaskOut]:
    return service.list_downloads(db)


@router.post("", response_model=None)
def post_downloads(
    db: DbSession, storage: StorageRootDep, data: DownloadCreate
) -> TaskOut | list[DownloadTaskOut] | JSONResponse:
    """Start a series download, or apply a bulk queue action.

    * ``{ seriesId }`` — plan + drain (202 + TaskOut).
    * ``{ action: "pause-all" | "cancel-all" | "resume-all" }`` — mutates the queue
      (200 + refreshed download list).
    """
    if data.action:
        return service.bulk_action(db, data.action, storage)
    if not data.series_id:
        raise BadRequestError("seriesId is required unless action is set")
    task = service.create_downloads(
        db,
        data.series_id,
        storage,
        provider_chapter_ids=data.provider_chapter_ids,
    )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=task.model_dump(by_alias=True, mode="json"),
    )


@router.post("/clear-completed", status_code=status.HTTP_204_NO_CONTENT)
def clear_completed(db: DbSession) -> Response:
    service.clear_completed(db)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{task_id}/retry", status_code=status.HTTP_202_ACCEPTED)
def retry_download(db: DbSession, storage: StorageRootDep, task_id: str) -> TaskOut:
    return service.retry_download(db, task_id, storage)


@router.post("/{task_id}/pause")
def pause_download(db: DbSession, task_id: str) -> list[DownloadTaskOut]:
    """Hold a queued chapter; returns the refreshed download list."""
    return service.pause_download(db, task_id)


@router.post("/{task_id}/resume")
def resume_download(db: DbSession, storage: StorageRootDep, task_id: str) -> list[DownloadTaskOut]:
    """Re-queue a paused chapter and start draining; returns the refreshed download list."""
    return service.resume_download(db, task_id, storage)


@router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_download(db: DbSession, task_id: str) -> Response:
    service.delete_download(db, task_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
