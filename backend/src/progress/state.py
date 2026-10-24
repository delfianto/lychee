"""Shared read state for local and provider-only chapters; no network or tracker side effects."""

from sqlalchemy import exists, func, or_, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from src.catalog.models import Chapter
from src.core.persistence.base_model import utc_now
from src.progress.models import ProviderReadingProgress, ReadingProgress


def provider_completed():
    return exists().where(
        ProviderReadingProgress.series_id == Chapter.series_id,
        ProviderReadingProgress.provider_chapter_id == Chapter.provider_chapter_id,
        ProviderReadingProgress.completed.is_(True),
    )


def chapter_completed():
    return or_(
        exists().where(
            ReadingProgress.chapter_id == Chapter.id, ReadingProgress.completed.is_(True)
        ),
        provider_completed(),
    )


def provider_states(session: Session, series_id: str) -> dict[str, ProviderReadingProgress]:
    return {
        row.provider_chapter_id: row
        for row in session.scalars(
            select(ProviderReadingProgress).where(ProviderReadingProgress.series_id == series_id)
        )
    }


def write_state(
    session: Session,
    *,
    series_id: str,
    chapter: Chapter | None,
    provider: str | None,
    provider_chapter_id: str | None,
    page: int,
    completed: bool | None,
) -> bool:
    """Ordinary page saves are monotonic; explicit completion/unread actions may reset state."""
    local = (
        session.scalar(select(ReadingProgress).where(ReadingProgress.chapter_id == chapter.id))
        if chapter
        else None
    )
    remote = (
        session.scalar(
            select(ProviderReadingProgress).where(
                ProviderReadingProgress.series_id == series_id,
                ProviderReadingProgress.provider == provider,
                ProviderReadingProgress.provider_chapter_id == provider_chapter_id,
            )
        )
        if provider and provider_chapter_id
        else None
    )
    was_read = bool((local and local.completed) or (remote and remote.completed))
    done = (
        completed
        if completed is not None
        else was_read or bool(chapter and chapter.page_count > 0 and page >= chapter.page_count)
    )
    # Atomic SQLite upserts prevent an older in-flight save from clearing a
    # completion or moving the furthest page backwards, even across requests.
    targets = []
    if chapter:
        targets.append(
            (ReadingProgress, {"chapter_id": chapter.id, "series_id": series_id}, ["chapter_id"])
        )
    if provider and provider_chapter_id:
        targets.append(
            (
                ProviderReadingProgress,
                {
                    "series_id": series_id,
                    "provider": provider,
                    "provider_chapter_id": provider_chapter_id,
                },
                ["series_id", "provider", "provider_chapter_id"],
            )
        )
    for model, identity, keys in targets:
        values = {**identity, "current_page": page, "completed": done}
        statement = insert(model).values(**values)
        changes = {
            "current_page": page if completed is not None else func.max(model.current_page, page),
            "completed": done
            if completed is not None
            else or_(model.completed, statement.excluded.completed),
            "updated_at": utc_now(),
        }
        session.execute(statement.on_conflict_do_update(index_elements=keys, set_=changes))
    session.expire_all()
    return was_read != done
