"""Measured scalar and grouped strategies for current series statistics."""

from typing import Any

from sqlalchemy import and_, case, func, select

from src.catalog.models import Chapter, ProviderChapter, Series
from src.progress.models import ProviderReadingProgress, ReadingProgress
from src.progress.state import provider_completed


def chapter_publication_date() -> Any:
    """Prefer source publication, including a cached date for older local downloads."""
    cached = (
        select(ProviderChapter.published_at)
        .where(
            ProviderChapter.series_id == Chapter.series_id,
            ProviderChapter.provider == func.coalesce(Chapter.provider, Series.provider),
            ProviderChapter.provider_chapter_id == Chapter.provider_chapter_id,
        )
        .correlate(Chapter, Series)
        .scalar_subquery()
    )
    return func.coalesce(Chapter.source_uploaded_at, cached, Chapter.created_at)


def chapter_stats(series_ids: Any, *, reads: bool = True, dates: bool = True) -> Any:
    statement = select(Chapter.series_id)
    if reads:
        completed = (
            select(
                ProviderReadingProgress.series_id,
                ProviderReadingProgress.provider_chapter_id,
            )
            .where(ProviderReadingProgress.completed.is_(True))
            .distinct()
            .subquery()
        )
        if series_ids is not None:
            completed = select(completed).where(completed.c.series_id.in_(series_ids)).subquery()
        statement = (
            statement.outerjoin(ReadingProgress, ReadingProgress.chapter_id == Chapter.id)
            .outerjoin(
                completed,
                and_(
                    completed.c.series_id == Chapter.series_id,
                    completed.c.provider_chapter_id == Chapter.provider_chapter_id,
                ),
            )
            .add_columns(
                func.count().label("chapter_count"),
                func.sum(
                    case(
                        (ReadingProgress.completed.is_(True), 0),
                        (completed.c.series_id.is_not(None), 0),
                        else_=1,
                    )
                ).label("unread_count"),
                func.max(
                    case((ReadingProgress.chapter_id.is_not(None), Chapter.number_sort))
                ).label("last_read"),
            )
        )
    if dates:
        statement = statement.add_columns(
            func.max(Chapter.created_at).label("local_update"),
            func.max(Chapter.source_uploaded_at).label("source_update"),
        )
    if series_ids is not None:
        statement = statement.where(Chapter.series_id.in_(series_ids))
    return statement.group_by(Chapter.series_id).subquery()


def provider_dates(series_ids: Any) -> Any:
    statement = select(
        ProviderChapter.series_id,
        func.max(ProviderChapter.published_at).label("provider_update"),
    ).where(ProviderChapter.provider == "mangadex")
    if series_ids is not None:
        statement = statement.where(ProviderChapter.series_id.in_(series_ids))
    return statement.group_by(ProviderChapter.series_id).subquery()


def content_updated_at(provider: Any, created: Any, local: Any, source: Any, remote: Any) -> Any:
    """MangaDex publication timeline, with the existing local/series fallbacks."""
    latest_source = case((source > remote, source), else_=func.coalesce(remote, source))
    return case(
        (provider == "mangadex", func.coalesce(latest_source, local, created)),
        else_=func.coalesce(local, created),
    )


def correlated_stats() -> tuple[Any, Any, Any, Any]:
    """SQLite's indexed scalar lookups outperform whole-scope grouping."""
    count = (
        select(func.count())
        .where(Chapter.series_id == Series.id)
        .correlate(Series)
        .scalar_subquery()
    )
    unread = (
        select(func.count())
        .select_from(Chapter)
        .outerjoin(
            ReadingProgress,
            and_(ReadingProgress.chapter_id == Chapter.id, ReadingProgress.completed.is_(True)),
        )
        .where(
            Chapter.series_id == Series.id,
            ReadingProgress.chapter_id.is_(None),
            ~provider_completed(),
        )
        .correlate(Series)
        .scalar_subquery()
    )
    last = (
        select(func.max(Chapter.number_sort))
        .join(ReadingProgress, ReadingProgress.chapter_id == Chapter.id)
        .where(Chapter.series_id == Series.id)
        .correlate(Series)
        .scalar_subquery()
    )
    local = (
        select(func.max(Chapter.created_at))
        .where(Chapter.series_id == Series.id)
        .correlate(Series)
        .scalar_subquery()
    )
    source = (
        select(func.max(Chapter.source_uploaded_at))
        .where(Chapter.series_id == Series.id)
        .correlate(Series)
        .scalar_subquery()
    )
    remote = (
        select(func.max(ProviderChapter.published_at))
        .where(ProviderChapter.series_id == Series.id, ProviderChapter.provider == Series.provider)
        .correlate(Series)
        .scalar_subquery()
    )
    return (
        count,
        unread,
        last,
        content_updated_at(
            Series.provider,
            Series.created_at,
            local,
            source,
            remote,
        ),
    )
