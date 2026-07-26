"""Reading-progress service. Drives unread / lastRead / continue-reading."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.models import Chapter
from src.core.exceptions import NotFoundError
from src.progress.models import ReadingProgress
from src.trackers.sync import enqueue_push


def update_progress(
    session: Session, chapter_id: str, page: int, completed: bool | None = None
) -> None:
    """Upsert this user's position in a chapter; completing recomputes unread."""
    chapter = session.get(Chapter, chapter_id)
    if chapter is None:
        raise NotFoundError(f"chapter {chapter_id!r} not found")

    done = (
        completed
        if completed is not None
        else (chapter.page_count > 0 and page >= chapter.page_count)
    )
    row = session.scalar(select(ReadingProgress).where(ReadingProgress.chapter_id == chapter_id))
    if row is None:
        row = ReadingProgress(chapter_id=chapter_id, series_id=chapter.series_id)
        session.add(row)
    row.series_id = chapter.series_id
    row.current_page = max(0, page)
    row.completed = done
    session.commit()
    if done:  # push read progress to connected trackers (background, best-effort)
        enqueue_push(session, chapter.series_id)
