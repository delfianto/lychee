"""Reading-progress API."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from src.core.persistence.database import DbSession
from src.progress import service
from src.progress.schema import ProgressUpdate

router = APIRouter(prefix="/api", tags=["progress"])


@router.put("/chapters/{chapter_id}/progress", status_code=status.HTTP_204_NO_CONTENT)
def update_progress(db: DbSession, chapter_id: str, data: ProgressUpdate) -> Response:
    """Record reading position; completing marks the chapter read."""
    service.update_progress(db, chapter_id, data.page, data.completed)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
