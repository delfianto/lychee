"""Reading progress, with durable local/provider identities and atomic manual batch changes."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.models import Chapter, ProviderChapter, Series
from src.core.exceptions import BadRequestError, NotFoundError
from src.progress.state import write_state
from src.trackers.sync import enqueue_push


def _resolve(
    session: Session, chapter_id: str
) -> tuple[Series, Chapter | None, str | None, str | None]:
    if chapter_id.startswith("adhoc:"):
        parts = chapter_id.split(":", 2)
        if len(parts) != 3 or not parts[1] or not parts[2]:
            raise BadRequestError("Invalid ad-hoc chapter ID")
        series = session.get(Series, parts[1])
        remote = session.scalar(
            select(ProviderChapter).where(
                ProviderChapter.series_id == parts[1],
                ProviderChapter.provider_chapter_id == parts[2],
            )
        )
        if series is None or remote is None:
            raise NotFoundError("Provider chapter not found")
        local = session.scalar(
            select(Chapter).where(
                Chapter.series_id == series.id,
                Chapter.provider_chapter_id == remote.provider_chapter_id,
            )
        )
        return series, local, remote.provider, remote.provider_chapter_id
    chapter = session.get(Chapter, chapter_id)
    if chapter is None:
        raise NotFoundError(f"chapter {chapter_id!r} not found")
    series = session.get(Series, chapter.series_id)
    if series is None:
        raise NotFoundError("Series not found")
    return series, chapter, chapter.provider or series.provider, chapter.provider_chapter_id


def update_progress(
    session: Session, chapter_id: str, page: int, completed: bool | None = None
) -> None:
    series, chapter, provider, remote_id = _resolve(session, chapter_id)
    changed = write_state(
        session,
        series_id=series.id,
        chapter=chapter,
        provider=provider,
        provider_chapter_id=remote_id,
        page=max(0, page),
        completed=completed,
    )
    session.commit()
    if changed:
        enqueue_push(session, series.id)


def mark_chapters(session: Session, series_id: str, chapter_ids: list[str], completed: bool) -> int:
    # Validate the complete selection before changing any chapter.
    resolved = [_resolve(session, chapter_id) for chapter_id in dict.fromkeys(chapter_ids)]
    if any(series.id != series_id for series, *_ in resolved):
        raise BadRequestError("All chapters must belong to this series")
    changed = False
    for series, chapter, provider, remote_id in resolved:
        changed = (
            write_state(
                session,
                series_id=series.id,
                chapter=chapter,
                provider=provider,
                provider_chapter_id=remote_id,
                page=chapter.page_count if completed and chapter else 0,
                completed=completed,
            )
            or changed
        )
    session.commit()
    if changed:
        enqueue_push(session, series_id)
    return len(resolved)
