"""Catalog queries — the series grid (filters + sort + keyset pagination) and detail.

Candidate selection computes only the statistics needed by sorting/filtering.
Display statistics are grouped once over the selected IDs, then hydrated in order.
Pagination is keyset (stable under infinite scroll): the cursor holds the sort
value + id of the last row, and the next page is everything ordered after it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, and_, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from src.catalog.models import Book, Chapter, Series, SeriesCredit
from src.catalog.search_index import search_ids
from src.catalog.series_stats import (
    chapter_stats,
    content_updated_at,
    correlated_stats,
    provider_dates,
)
from src.core.schema import decode_cursor, encode_cursor
from src.progress.models import ReadingProgress
from src.progress.state import chapter_completed
from src.taxonomy.models import series_tag

_TIME_SORTS = frozenset({"recentlyAdded", "recentlyUpdated"})


@dataclass(slots=True)
class SeriesFilters:
    """Parsed filters for the series grid (see PART C of the plan)."""

    kind: str | None = None
    library_id: str | None = None
    shelf: str | None = None
    favorite: bool | None = None
    q: str | None = None
    ids: list[str] | None = None  # restrict to these series (FTS search hydration)
    tags_include: list[str] = field(default_factory=list)
    tags_exclude: list[str] = field(default_factory=list)
    tag_mode: str = "and"
    ratings: list[str] = field(default_factory=list)
    demographics: list[str] = field(default_factory=list)
    pub_status: list[str] = field(default_factory=list)
    read_state: str | None = None
    artist: str | None = None
    author: str | None = None
    source: str | None = None
    sort: str = "recentlyAdded"


@dataclass(slots=True)
class SeriesRow:
    """A series plus its derived counts for one grid row."""

    series: Series
    chapter_count: int
    unread_count: int
    last_read: float | None
    content_updated_at: datetime


def _sort_value(sort: str, row: SeriesRow) -> Any:
    if sort == "title":
        return row.series.sort_title
    if sort == "rating":
        return row.series.rating if row.series.rating is not None else -1.0
    if sort == "unread":
        return row.unread_count
    return row.content_updated_at if sort == "recentlyUpdated" else row.series.created_at


def _conditions(f: SeriesFilters) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = []
    if f.kind:
        kinds = ["comic" if part == "comics" else part for part in f.kind.split(",") if part]
        if len(kinds) == 1:
            conds.append(Series.kind == kinds[0])
        elif kinds:
            conds.append(Series.kind.in_(kinds))
    if f.library_id is not None:
        conds.append(Series.library_id == f.library_id)
    if f.shelf:
        conds.append(Series.library_status == f.shelf)
    if f.favorite is not None:
        conds.append(Series.favorite.is_(f.favorite))
    if f.q:
        conds.append(Series.title.ilike(f"%{f.q}%"))
    if f.ids is not None:
        conds.append(Series.id.in_(f.ids))
    if f.ratings:
        conds.append(Series.content_rating.in_(f.ratings))
    if f.demographics:
        conds.append(Series.demographic.in_(f.demographics))
    if f.pub_status:
        conds.append(Series.status.in_(f.pub_status))
    if f.source:
        conds.append(Series.source == f.source)
    for role, name in [("author", f.author), ("artist", f.artist)]:
        if name and name.strip():
            conds.append(
                exists().where(
                    SeriesCredit.series_id == Series.id,
                    SeriesCredit.role == role,
                    func.lower(SeriesCredit.name).contains(name.strip().lower(), autoescape=True),
                )
            )
    if f.tags_include:
        if f.tag_mode == "or":
            conds.append(
                exists().where(
                    series_tag.c.series_id == Series.id,
                    series_tag.c.tag_id.in_(f.tags_include),
                )
            )
        else:
            conds.extend(
                exists().where(series_tag.c.series_id == Series.id, series_tag.c.tag_id == tid)
                for tid in f.tags_include
            )
    if f.tags_exclude:
        conds.append(
            ~exists().where(
                series_tag.c.series_id == Series.id,
                series_tag.c.tag_id.in_(f.tags_exclude),
            )
        )
    return conds


def list_series(
    session: Session,
    filters: SeriesFilters,
    *,
    cursor: str | None = None,
    limit: int = 24,
) -> tuple[list[SeriesRow], str | None]:
    """Return one page of grid rows and the cursor for the next page (or None)."""
    conditions = _conditions(filters)
    # Kind-only grids need most chapter groups anyway. Avoid forcing a repeated
    # series/index traversal inside their global rollups; narrower filters scope
    # the rollups before aggregation.
    eligible = (
        select(Series.id).where(*conditions).correlate(None)
        if _conditions(replace(filters, kind=None))
        else None
    )
    grouped = session.get_bind().dialect.driver == "turso"
    scalar = None if grouped else correlated_stats()
    statement = select(Series.id)
    reads = None
    unread = None
    if filters.sort == "unread" or filters.read_state in {"unread", "read", "in_progress"}:
        if grouped and filters.sort not in {"recentlyAdded", "title"}:
            reads = chapter_stats(eligible, dates=False)
            statement = statement.outerjoin(reads, reads.c.series_id == Series.id)
            unread = func.coalesce(reads.c.unread_count, 0)
        else:
            unread = correlated_stats()[1] if scalar is None else scalar[1]
        if filters.read_state in {"unread", "in_progress"}:
            conditions.append(unread > 0)
        elif filters.read_state == "read":
            conditions.append(unread == 0)
        if filters.read_state == "in_progress":
            conditions.append(exists().where(ReadingProgress.series_id == Series.id))

    descending = filters.sort != "title"
    if filters.sort == "title":
        order_expr = Series.sort_title
    elif filters.sort == "rating":
        order_expr = func.coalesce(Series.rating, -1.0)
    elif filters.sort == "unread":
        assert unread is not None
        order_expr = unread
    elif filters.sort == "recentlyUpdated":
        if grouped:
            dates = chapter_stats(eligible, reads=False)
            remote = provider_dates(eligible)
            statement = statement.outerjoin(dates, dates.c.series_id == Series.id).outerjoin(
                remote, remote.c.series_id == Series.id
            )
            order_expr = content_updated_at(
                Series.provider,
                Series.created_at,
                dates.c.local_update,
                dates.c.source_update,
                remote.c.provider_update,
            )
        else:
            assert scalar is not None
            order_expr = scalar[3]
    else:
        order_expr = Series.created_at
    statement = statement.add_columns(order_expr.label("sort_value")).where(*conditions)
    if cursor is not None:
        data = decode_cursor(cursor)
        value: Any = data["v"]
        last_id: str = data["id"]
        if filters.sort in _TIME_SORTS and isinstance(value, str):
            value = datetime.fromisoformat(value)
        statement = statement.where(
            or_(order_expr < value, and_(order_expr == value, Series.id < last_id))
            if descending
            else or_(order_expr > value, and_(order_expr == value, Series.id > last_id))
        )
    page = statement.order_by(
        order_expr.desc() if descending else order_expr.asc(),
        Series.id.desc() if descending else Series.id.asc(),
    ).limit(limit + 1)
    if grouped:
        candidates = [(row.id, row.sort_value) for row in session.execute(page)]
        hydrated = get_series_rows(session, [sid for sid, _ in candidates[:limit]])
        rows = [hydrated[sid] for sid, _ in candidates[:limit] if sid in hydrated]
    else:
        assert scalar is not None
        selected_page = page.with_only_columns(Series.id).subquery()
        statement = (
            select(Series, *scalar)
            .join(selected_page, selected_page.c.id == Series.id)
            .order_by(
                order_expr.desc() if descending else order_expr.asc(),
                Series.id.desc() if descending else Series.id.asc(),
            )
            .options(selectinload(Series.tags), selectinload(Series.credits))
        )
        results = session.execute(statement).all()
        all_rows = [SeriesRow(row[0], row[1], row[2], row[3], row[4]) for row in results]
        candidates = [(row.series.id, _sort_value(filters.sort, row)) for row in all_rows]
        rows = all_rows[:limit]
    next_cursor = None
    if len(candidates) > limit:
        # Retain the selection boundary if concurrent edits change hydration.
        last_id, value = candidates[limit - 1]
        if isinstance(value, datetime):
            value = value.isoformat()
        next_cursor = encode_cursor({"v": value, "id": last_id})
    return rows, next_cursor


def get_series(session: Session, series_id: str) -> SeriesRow | None:
    """Fetch a single series with its derived counts, or None."""
    return get_series_rows(session, [series_id]).get(series_id)


def get_series_rows(session: Session, series_ids: list[str]) -> dict[str, SeriesRow]:
    """Hydrate display statistics once over a bounded set of IDs."""
    if not series_ids:
        return {}
    series_ids = list(dict.fromkeys(series_ids))
    if session.get_bind().dialect.driver == "turso":
        local = chapter_stats(series_ids)
        remote = provider_dates(series_ids)
        statement = (
            select(
                Series,
                func.coalesce(local.c.chapter_count, 0),
                func.coalesce(local.c.unread_count, 0),
                local.c.last_read,
                content_updated_at(
                    Series.provider,
                    Series.created_at,
                    local.c.local_update,
                    local.c.source_update,
                    remote.c.provider_update,
                ),
            )
            .outerjoin(local, local.c.series_id == Series.id)
            .outerjoin(remote, remote.c.series_id == Series.id)
        )
    else:
        statement = select(Series, *correlated_stats())
    statement = statement.where(Series.id.in_(series_ids)).options(
        selectinload(Series.tags), selectinload(Series.credits)
    )
    return {
        row[0].id: SeriesRow(row[0], row[1], row[2], row[3], row[4])
        for row in session.execute(statement).all()
    }


# --- chapters -------------------------------------------------------------------


@dataclass(slots=True)
class ChapterRow:
    """A chapter plus whether it's been read."""

    chapter: Chapter
    read: bool


def _read_exists() -> ColumnElement[bool]:
    return chapter_completed()


def list_chapters(
    session: Session, series_id: str, *, language: str | None = None, descending: bool = True
) -> list[ChapterRow]:
    """All chapters of a series (optionally one language), ordered by number."""
    stmt = select(Chapter, _read_exists().label("read")).where(Chapter.series_id == series_id)
    if language:
        stmt = stmt.where(Chapter.language == language)
    stmt = stmt.order_by(
        Chapter.number_sort.desc() if descending else Chapter.number_sort.asc(),
        Chapter.id.desc() if descending else Chapter.id.asc(),
    )
    return [ChapterRow(chapter=r[0], read=bool(r[1])) for r in session.execute(stmt).all()]


def get_chapter(session: Session, chapter_id: str) -> ChapterRow | None:
    row = session.execute(
        select(Chapter, _read_exists().label("read")).where(Chapter.id == chapter_id)
    ).first()
    return ChapterRow(chapter=row[0], read=bool(row[1])) if row is not None else None


# --- update feeds ---------------------------------------------------------------


@dataclass(slots=True)
class UpdateRow:
    """A chapter update (chapter + effective timestamp) for the update feeds."""

    chapter: Chapter
    updated_at: datetime


def recent_updates(
    session: Session,
    *,
    unread_only: bool = False,
    cursor: str | None = None,
    limit: int = 24,
) -> tuple[list[UpdateRow], str | None]:
    """Chapter updates across chaptered series, newest first, keyset-paginated."""
    updated = func.coalesce(Chapter.source_uploaded_at, Chapter.created_at)
    stmt = (
        select(Chapter, updated.label("updated"))
        .join(Series, Series.id == Chapter.series_id)
        .where(Series.kind != "gallery")
    )
    if unread_only:
        stmt = stmt.where(~_read_exists())
    if cursor is not None:
        data = decode_cursor(cursor)
        value = datetime.fromisoformat(data["v"])
        last_id: str = data["id"]
        stmt = stmt.where(or_(updated < value, and_(updated == value, Chapter.id < last_id)))
    stmt = stmt.order_by(updated.desc(), Chapter.id.desc()).limit(limit + 1)

    rows = [UpdateRow(chapter=r[0], updated_at=r[1]) for r in session.execute(stmt).all()]
    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor({"v": last.updated_at.isoformat(), "id": last.chapter.id})
    return rows, next_cursor


# --- dashboard ------------------------------------------------------------------


def dashboard_counts(session: Session) -> tuple[int, int, int]:
    """(total series, total unread chapters, series currently reading) — chaptered only."""
    series_count = (
        session.scalar(select(func.count(Series.id)).where(Series.kind != "gallery")) or 0
    )
    unread_chapters = (
        session.scalar(
            select(func.count(Chapter.id))
            .join(Series, Series.id == Chapter.series_id)
            .where(Series.kind != "gallery", ~_read_exists())
        )
        or 0
    )
    reading = (
        session.scalar(select(func.count(Series.id)).where(Series.library_status == "reading")) or 0
    )
    return series_count, unread_chapters, reading


def continue_reading(session: Session, *, limit: int = 6) -> list[SeriesRow]:
    """Series with progress and something still unread, most-recently-read first."""
    progress = (
        select(
            ReadingProgress.series_id, func.max(ReadingProgress.updated_at).label("last_progress")
        )
        .group_by(ReadingProgress.series_id)
        .subquery()
    )
    eligible = select(progress.c.series_id)
    reads = chapter_stats(eligible, dates=False)
    ids = list(
        session.scalars(
            select(Series.id)
            .join(progress, progress.c.series_id == Series.id)
            .join(reads, reads.c.series_id == Series.id)
            .where(reads.c.unread_count > 0)
            .order_by(progress.c.last_progress.desc(), Series.id.desc())
            .limit(limit)
        )
    )
    rows = get_series_rows(session, ids)
    return [rows[sid] for sid in ids if sid in rows]


def recently_added(
    session: Session,
    *,
    kinds: Sequence[str] = ("manga",),
    limit: int = 12,
) -> list[SeriesRow]:
    """Newest series first for the configured kinds, for the dashboard rail."""
    if not kinds:
        return []
    return list_series(session, SeriesFilters(kind=",".join(kinds)), limit=limit)[0]


def search_series(
    session: Session,
    q: str,
    *,
    limit: int = 20,
    author: str | None = None,
    artist: str | None = None,
) -> list[SeriesRow]:
    """Full-text search over title / alt-titles / authors (FTS5 trigram, ranked).

    Falls back to a title LIKE match when FTS can't serve the query (index absent,
    or a query too short to yield trigrams). FTS gives ranked ids; the grid builder
    hydrates them (counts, tags, credits) and we restore the relevance order.
    """
    if author or artist:
        return list_series(
            session,
            SeriesFilters(q=q or None, author=author, artist=artist, sort="title"),
            limit=limit,
        )[0]
    ranked = search_ids(session, q, limit=limit)
    if ranked is None:
        rows, _ = list_series(session, SeriesFilters(q=q, sort="title"), limit=limit)
        return rows
    if not ranked:
        return []
    rows, _ = list_series(session, SeriesFilters(ids=ranked), limit=len(ranked))
    rank = {sid: i for i, sid in enumerate(ranked)}
    rows.sort(key=lambda row: rank.get(row.series.id, len(ranked)))
    return rows


def library_size_by_kind(session: Session) -> list[tuple[str, int]]:
    """Total stored bytes grouped by series kind (for the storage summary)."""
    rows = session.execute(
        select(Series.kind, func.coalesce(func.sum(Book.file_size), 0))
        .join(Book, Book.series_id == Series.id)
        .group_by(Series.kind)
    ).all()
    return [(r[0], int(r[1])) for r in rows]


def related_series(session: Session, series_id: str, *, limit: int = 12) -> list[SeriesRow]:
    """Other series of the same kind, newest first (excludes the series itself)."""
    series = session.get(Series, series_id)
    if series is None:
        return []
    ids = list(
        session.scalars(
            select(Series.id)
            .where(Series.kind == series.kind, Series.id != series_id)
            .order_by(Series.created_at.desc(), Series.id.desc())
            .limit(limit)
        ).all()
    )
    rows = get_series_rows(session, ids)
    return [rows[i] for i in ids if i in rows]


def creator_names(session: Session, role: str, q: str, *, limit: int = 20) -> list[str]:
    statement = select(SeriesCredit.name).where(SeriesCredit.role == role)
    if q.strip():
        statement = statement.where(
            func.lower(SeriesCredit.name).contains(q.strip().lower(), autoescape=True)
        )
    return list(
        session.scalars(
            statement.distinct()
            .order_by(func.lower(SeriesCredit.name), SeriesCredit.name)
            .limit(max(1, min(limit, 50)))
        )
    )
