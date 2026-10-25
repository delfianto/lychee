"""Bounded Home shelves: select identities first, then hydrate just the visible page.

Discovery ranks eligible IDs with a daily seed; it never loads the whole library's
metadata or reaches out to a provider. Reading shelves include durable remote reads.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, exists, func, literal, or_, select, union_all
from sqlalchemy.orm import Session, aliased

from src.catalog import repository as repo
from src.catalog.models import Book, Chapter, ProviderChapter, Series
from src.catalog.presentation import to_series_out
from src.catalog.schema import HomeSection, HomeSectionOut, HomeSeriesOut, RecentUpdateOut
from src.catalog.series_stats import chapter_publication_date
from src.core.exceptions import BadRequestError
from src.core.schema import decode_cursor, encode_cursor
from src.progress.models import ProviderReadingProgress, ReadingProgress
from src.progress.state import chapter_completed
from src.taxonomy.models import series_tag


def _remote_read():
    provider = (
        exists()
        .where(
            ProviderReadingProgress.series_id == ProviderChapter.series_id,
            ProviderReadingProgress.provider == ProviderChapter.provider,
            ProviderReadingProgress.provider_chapter_id == ProviderChapter.provider_chapter_id,
            ProviderReadingProgress.completed.is_(True),
        )
        .correlate(ProviderChapter)
    )
    local = (
        exists()
        .where(
            Chapter.series_id == ProviderChapter.series_id,
            Chapter.provider_chapter_id == ProviderChapter.provider_chapter_id,
            ReadingProgress.chapter_id == Chapter.id,
            ReadingProgress.completed.is_(True),
        )
        .correlate(ProviderChapter)
    )
    return or_(provider, local)


def _activity():
    events = union_all(
        select(ReadingProgress.series_id, ReadingProgress.updated_at.label("at")).where(
            or_(ReadingProgress.current_page > 0, ReadingProgress.completed.is_(True))
        ),
        select(ProviderReadingProgress.series_id, ProviderReadingProgress.updated_at.label("at"))
        .join(Series, Series.id == ProviderReadingProgress.series_id)
        .where(
            ProviderReadingProgress.provider == Series.provider,
            or_(
                ProviderReadingProgress.current_page > 0,
                ProviderReadingProgress.completed.is_(True),
            ),
        ),
    ).subquery()
    return (
        select(events.c.series_id, func.max(events.c.at).label("at"))
        .group_by(events.c.series_id)
        .subquery()
    )


def _live_chapters():
    return (
        select(Chapter)
        .join(Book, Book.id == Chapter.book_id)
        .where(Book.deleted_at.is_(None), Chapter.page_count > 0)
    )


def _quick_candidates(kind: str):
    pages = (
        select(
            Chapter.series_id,
            func.sum(Chapter.page_count).label("pages"),
            func.count().label("chapters"),
        )
        .join(Book, Book.id == Chapter.book_id)
        .where(Book.deleted_at.is_(None))
        .group_by(Chapter.series_id)
        # A corrupt/unknown page count must not masquerade as a short read.
        .having(func.min(Chapter.page_count) > 0, func.sum(Chapter.page_count) <= 200)
        .subquery()
    )
    oneshot = exists().where(series_tag.c.series_id == Series.id, series_tag.c.tag_id == "oneshot")
    started = _activity()
    downloaded = (
        select(Chapter.id)
        .join(Book, Book.id == Chapter.book_id)
        .where(
            Chapter.series_id == ProviderChapter.series_id,
            Chapter.provider_chapter_id == ProviderChapter.provider_chapter_id,
            Book.deleted_at.is_(None),
            Chapter.page_count > 0,
        )
        .correlate(ProviderChapter)
        .exists()
    )
    missing = exists().where(
        ProviderChapter.series_id == Series.id,
        ProviderChapter.provider == Series.provider,
        ProviderChapter.language == func.coalesce(Series.chapter_index_language, "en"),
        ~downloaded,
    )
    return (
        select(Series.id, pages.c.pages)
        .join(pages, pages.c.series_id == Series.id)
        .where(
            Series.kind == kind,
            Series.library_status.not_in(("dropped", "completed")),
            Series.available_chapters == 0,
            or_(Series.total_chapters.is_(None), Series.total_chapters <= pages.c.chapters),
            ~select(Chapter.id)
            .join(Book, Book.id == Chapter.book_id)
            .where(Chapter.series_id == Series.id, Book.deleted_at.is_not(None))
            .exists(),
            ~missing,
            or_(Series.status == "completed", oneshot),
            ~Series.id.in_(select(started.c.series_id)),
        )
    )


def _resume_targets(session: Session, ids: list[str]) -> dict[str, tuple[str, str]]:
    """Rank candidates in SQL; return one target per visible work, never every chapter."""
    position = aliased(ReadingProgress)
    provider_position = aliased(ProviderReadingProgress)
    local = (
        select(
            Chapter.series_id.label("series_id"),
            Chapter.id.label("target"),
            func.coalesce(Chapter.number, Chapter.title, "Oneshot").label("label"),
            Chapter.number_sort.label("number"),
            func.max(
                func.coalesce(position.current_page, 0),
                func.coalesce(provider_position.current_page, 0),
            ).label("page"),
            case(
                (position.updated_at > provider_position.updated_at, position.updated_at),
                else_=func.coalesce(provider_position.updated_at, position.updated_at),
            ).label("at"),
            literal(0).label("source"),
        )
        .join(Book, Book.id == Chapter.book_id)
        .join(Series, Series.id == Chapter.series_id)
        .outerjoin(position, position.chapter_id == Chapter.id)
        .outerjoin(
            provider_position,
            and_(
                provider_position.series_id == Chapter.series_id,
                provider_position.provider == func.coalesce(Chapter.provider, Series.provider),
                provider_position.provider_chapter_id == Chapter.provider_chapter_id,
            ),
        )
        .where(
            Chapter.series_id.in_(ids),
            Book.deleted_at.is_(None),
            Chapter.page_count > 0,
            ~chapter_completed(),
        )
    )
    remote = (
        select(
            ProviderChapter.series_id,
            (
                literal("adhoc:")
                + ProviderChapter.series_id
                + literal(":")
                + ProviderChapter.provider_chapter_id
            ),
            func.coalesce(ProviderChapter.number, ProviderChapter.title, "Oneshot"),
            ProviderChapter.number_sort,
            func.coalesce(provider_position.current_page, 0),
            provider_position.updated_at,
            literal(1),
        )
        .join(Series, Series.id == ProviderChapter.series_id)
        .outerjoin(
            provider_position,
            and_(
                provider_position.series_id == ProviderChapter.series_id,
                provider_position.provider == ProviderChapter.provider,
                provider_position.provider_chapter_id == ProviderChapter.provider_chapter_id,
            ),
        )
        .where(
            ProviderChapter.series_id.in_(ids),
            ProviderChapter.provider == Series.provider,
            ProviderChapter.language == func.coalesce(Series.chapter_index_language, "en"),
            ~_remote_read(),
            ~_live_chapters()
            .where(
                Chapter.series_id == ProviderChapter.series_id,
                Chapter.provider_chapter_id == ProviderChapter.provider_chapter_id,
            )
            .correlate(ProviderChapter)
            .exists(),
        )
    )
    candidates = union_all(local, remote).subquery()
    ranked = select(
        candidates,
        func.row_number()
        .over(
            partition_by=candidates.c.series_id,
            order_by=(
                case((candidates.c.page > 0, 0), else_=1),
                case((candidates.c.page > 0, candidates.c.at)).desc(),
                candidates.c.number.asc().nulls_last(),
                candidates.c.source,
                candidates.c.target,
            ),
        )
        .label("rank"),
    ).subquery()
    return {
        row.series_id: (row.target, row.label)
        for row in session.execute(select(ranked).where(ranked.c.rank == 1))
    }


def _out(session: Session, ids: list[str], *, pages: dict[str, int] | None = None, resume=False):
    rows = repo.get_series_rows(session, ids)
    targets = _resume_targets(session, ids) if resume and ids else {}
    return [
        HomeSeriesOut(
            **to_series_out(rows[sid]).model_dump(exclude={"description"}),
            page_count=(pages or {}).get(sid),
            resume_chapter_id=targets[sid][0] if sid in targets else None,
            resume_chapter_label=targets[sid][1] if sid in targets else None,
        )
        for sid in ids
        if sid in rows
    ]


def _cursor(cursor: str | None, shelf: str, seed: str) -> dict[str, Any] | None:
    if cursor is None:
        return None
    try:
        data = decode_cursor(cursor)
        if (
            data.get("shelf") != shelf
            or data.get("seed") != seed
            or not isinstance(data.get("id"), str)
            or not isinstance(data.get("v"), str)
        ):
            raise ValueError("cursor scope")
        return data
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        raise BadRequestError("Invalid home shelf cursor") from exc


def section(
    session: Session,
    shelf: HomeSection,
    *,
    cursor: str | None = None,
    limit: int = 24,
    kind: str = "manga",
    seed: str | None = None,
    recently_added_kinds: tuple[str, ...] = ("manga",),
    following: bool = False,
) -> HomeSectionOut:
    if shelf in {"readingList", "recentlyAdded"}:
        kinds = "manga,comic" if shelf == "readingList" else ",".join(recently_added_kinds)
        if not kinds:
            return HomeSectionOut()
        filters = repo.SeriesFilters(
            kind=kinds,
            shelf="reading" if shelf == "readingList" else None,
            sort="title" if shelf == "readingList" else "recentlyAdded",
        )
        scope = f"{shelf}:{kinds}"
        after = _cursor(cursor, scope, "")
        try:
            rows, next_cursor = repo.list_series(
                session, filters, cursor=after["v"] if after else None, limit=limit
            )
        except (ValueError, TypeError, KeyError) as exc:
            raise BadRequestError("Invalid home shelf cursor") from exc
        return HomeSectionOut(
            items=[
                HomeSeriesOut(**to_series_out(row).model_dump(exclude={"description"}))
                for row in rows
            ],
            next_cursor=encode_cursor({"shelf": scope, "seed": "", "id": "", "v": next_cursor})
            if next_cursor
            else None,
        )
    if shelf == "recentUpdates":
        return _updates(session, cursor=cursor, limit=limit, following=following)
    now = datetime.now(UTC)
    key_seed = seed or now.date().isoformat()
    scope = f"{shelf}:{kind}" if shelf != "continueReading" else shelf
    after = _cursor(cursor, scope, key_seed if shelf != "continueReading" else "")
    if shelf == "continueReading":
        activity = _activity()
        unread_local = (
            _live_chapters().where(Chapter.series_id == Series.id, ~chapter_completed()).exists()
        )
        unread_remote = exists().where(
            ProviderChapter.series_id == Series.id,
            ProviderChapter.provider == Series.provider,
            ProviderChapter.language == func.coalesce(Series.chapter_index_language, "en"),
            ~_remote_read(),
        )
        query = (
            select(Series.id, activity.c.at)
            .join(activity, activity.c.series_id == Series.id)
            .where(
                Series.kind.in_(("manga", "comic")),
                Series.library_status.not_in(("dropped", "completed")),
                or_(unread_local, unread_remote),
            )
        )
        if after:
            try:
                at = datetime.fromisoformat(after["v"])
            except ValueError as exc:
                raise BadRequestError("Invalid home shelf cursor") from exc
            query = query.where(
                or_(activity.c.at < at, and_(activity.c.at == at, Series.id < after["id"]))
            )
        candidates = list(
            session.execute(query.order_by(activity.c.at.desc(), Series.id.desc()).limit(limit + 1))
        )
        ids = [row[0] for row in candidates[:limit]]
        next_cursor = (
            encode_cursor(
                {
                    "shelf": scope,
                    "seed": "",
                    "id": ids[-1],
                    "v": candidates[limit - 1][1].isoformat(),
                }
            )
            if len(candidates) > limit
            else None
        )
        return HomeSectionOut(items=_out(session, ids, resume=True), next_cursor=next_cursor)
    pages = {}
    if shelf == "quickReads":
        candidates = list(session.execute(_quick_candidates(kind)))
        pages = {row[0]: int(row[1]) for row in candidates}
        ids = list(pages)
    else:
        activity = _activity()
        candidates = list(
            session.execute(
                select(Series.id, Series.created_at)
                .where(
                    Series.kind == kind,
                    Series.library_status.not_in(("dropped", "completed")),
                    ~Series.id.in_(select(activity.c.series_id)),
                    ~Series.id.in_(_quick_candidates(kind).with_only_columns(Series.id)),
                )
                .order_by(Series.created_at.asc(), Series.id.asc())
            )
        )
        old = [sid for sid, at in candidates if at.replace(tzinfo=UTC) < now - timedelta(days=30)]
        # Recently imported libraries still get discovery: leave the newest 24
        # eligible additions to Recently added and sample the older remainder.
        ids = old or [row[0] for row in candidates[:-24]]
    ranked = sorted((hashlib.blake2s(f"{key_seed}:{sid}".encode()).hexdigest(), sid) for sid in ids)
    if after:
        ranked = [entry for entry in ranked if entry > (after["v"], after["id"])]
    selected = [sid for _, sid in ranked[:limit]]
    next_cursor = (
        encode_cursor(
            {"shelf": scope, "seed": key_seed, "v": ranked[limit - 1][0], "id": selected[-1]}
        )
        if len(ranked) > limit
        else None
    )
    return HomeSectionOut(items=_out(session, selected, pages=pages), next_cursor=next_cursor)


def _updates(
    session: Session, *, cursor: str | None, limit: int, following: bool
) -> HomeSectionOut:
    scope = "updates:following" if following else "updates:all"
    after = _cursor(cursor, scope, "")
    local = (
        select(
            Chapter.series_id.label("series_id"),
            Chapter.id.label("id"),
            Chapter.volume.label("volume"),
            Chapter.number.label("number"),
            chapter_publication_date().label("at"),
        )
        .join(Book, Book.id == Chapter.book_id)
        .join(Series, Series.id == Chapter.series_id)
        .where(Book.deleted_at.is_(None))
    )
    remote = (
        select(
            ProviderChapter.series_id,
            ProviderChapter.id,
            ProviderChapter.volume,
            ProviderChapter.number,
            ProviderChapter.published_at,
        )
        .join(Series, Series.id == ProviderChapter.series_id)
        .where(
            ProviderChapter.provider == Series.provider,
            ProviderChapter.published_at.is_not(None),
            ProviderChapter.language == func.coalesce(Series.chapter_index_language, "en"),
            ~_live_chapters()
            .where(
                Chapter.series_id == ProviderChapter.series_id,
                Chapter.provider_chapter_id == ProviderChapter.provider_chapter_id,
            )
            .correlate(ProviderChapter)
            .exists(),
        )
    )
    changes = union_all(local, remote).subquery()
    query = (
        select(changes)
        .join(Series, Series.id == changes.c.series_id)
        .where(Series.kind.in_(("manga", "comic")))
    )
    if following:
        query = query.where(
            or_(Series.library_status.in_(("reading", "re_reading")), Series.favorite.is_(True))
        )
    if after:
        try:
            at = datetime.fromisoformat(after["v"])
        except ValueError as exc:
            raise BadRequestError("Invalid home shelf cursor") from exc
        query = query.where(
            or_(changes.c.at < at, and_(changes.c.at == at, changes.c.id < after["id"]))
        )
    candidates = list(
        session.execute(query.order_by(changes.c.at.desc(), changes.c.id.desc()).limit(limit + 1))
    )
    rows = candidates[:limit]
    series = repo.get_series_rows(session, [row.series_id for row in rows])
    return HomeSectionOut(
        updates=[
            RecentUpdateOut(
                series=to_series_out(series[row.series_id]).model_copy(
                    update={"description": None}
                ),
                volume=row.volume,
                chapter=row.number or "",
                updated_at=row.at,
            )
            for row in rows
            if row.series_id in series
        ],
        next_cursor=encode_cursor(
            {"shelf": scope, "seed": "", "id": rows[-1].id, "v": rows[-1].at.isoformat()}
        )
        if len(candidates) > limit
        else None,
    )
