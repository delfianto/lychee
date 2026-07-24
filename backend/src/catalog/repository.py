"""Catalog queries — the series grid (filters + sort + keyset pagination) and detail.

Per-series derived counts (chapter/unread/last-read) are correlated scalar
subqueries selected alongside each ``Series`` row, so one query drives the grid.
Pagination is keyset (stable under infinite scroll): the cursor holds the sort
value + id of the last row, and the next page is everything ordered after it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy import ColumnElement, and_, exists, func, or_, select
from sqlalchemy.orm import Session, selectinload

from src.catalog.models import Chapter, Series, SeriesCredit
from src.core.schema import decode_cursor, encode_cursor
from src.progress.models import ReadingProgress
from src.taxonomy.models import series_tag

_TIME_SORTS = frozenset({"recentlyAdded", "recentlyUpdated"})


@dataclass(slots=True)
class SeriesFilters:
    """Parsed filters for the series grid (see PART C of the plan)."""

    kind: str | None = None
    shelf: str | None = None
    favorite: bool | None = None
    q: str | None = None
    tags_include: list[str] = field(default_factory=list)
    tags_exclude: list[str] = field(default_factory=list)
    tag_mode: str = "and"
    ratings: list[str] = field(default_factory=list)
    demographics: list[str] = field(default_factory=list)
    pub_status: list[str] = field(default_factory=list)
    read_state: str | None = None
    artist: str | None = None
    source: str | None = None
    sort: str = "recentlyAdded"


@dataclass(slots=True)
class SeriesRow:
    """A series plus its derived counts for one grid row."""

    series: Series
    chapter_count: int
    unread_count: int
    last_read: float | None


@dataclass(slots=True)
class _Aggregates:
    chapter_count: ColumnElement[int]
    unread_count: ColumnElement[int]
    last_read: ColumnElement[Any]


def _aggregates() -> _Aggregates:
    chapter_count = (
        select(func.count(Chapter.id))
        .where(Chapter.series_id == Series.id)
        .correlate(Series)
        .scalar_subquery()
    )
    unread_count = (
        select(func.count(Chapter.id))
        .select_from(Chapter)
        .outerjoin(
            ReadingProgress,
            and_(ReadingProgress.chapter_id == Chapter.id, ReadingProgress.completed.is_(True)),
        )
        .where(Chapter.series_id == Series.id, ReadingProgress.chapter_id.is_(None))
        .correlate(Series)
        .scalar_subquery()
    )
    last_read = (
        select(func.max(Chapter.number_sort))
        .select_from(Chapter)
        .join(ReadingProgress, ReadingProgress.chapter_id == Chapter.id)
        .where(Chapter.series_id == Series.id)
        .correlate(Series)
        .scalar_subquery()
    )
    return _Aggregates(chapter_count, unread_count, last_read)


def _sort_expr(sort: str, agg: _Aggregates) -> tuple[Any, bool]:
    """Return (order expression, descending?) for a sort key.

    The expression is a mapped column, ``coalesce``, or the unread subquery — all
    valid order/compare operands, typed ``Any`` at this SQLAlchemy boundary.
    """
    if sort == "title":
        return Series.sort_title, False
    if sort == "recentlyUpdated":
        return Series.updated_at, True
    if sort == "rating":
        return func.coalesce(Series.rating, -1.0), True
    if sort == "unread":
        return agg.unread_count, True
    return Series.created_at, True  # recentlyAdded (default)


def _sort_value(sort: str, row: SeriesRow) -> object:
    """Extract a row's ordering value, for building the next-page cursor."""
    if sort == "title":
        return row.series.sort_title
    if sort == "recentlyUpdated":
        return row.series.updated_at.isoformat()
    if sort == "rating":
        return row.series.rating if row.series.rating is not None else -1.0
    if sort == "unread":
        return row.unread_count
    return row.series.created_at.isoformat()


def _conditions(f: SeriesFilters, agg: _Aggregates) -> list[ColumnElement[bool]]:
    conds: list[ColumnElement[bool]] = []
    if f.kind:
        conds.append(Series.kind == f.kind)
    if f.shelf:
        conds.append(Series.library_status == f.shelf)
    if f.favorite is not None:
        conds.append(Series.favorite.is_(f.favorite))
    if f.q:
        conds.append(Series.title.ilike(f"%{f.q}%"))
    if f.ratings:
        conds.append(Series.content_rating.in_(f.ratings))
    if f.demographics:
        conds.append(Series.demographic.in_(f.demographics))
    if f.pub_status:
        conds.append(Series.status.in_(f.pub_status))
    if f.source:
        conds.append(Series.source == f.source)
    if f.artist:
        conds.append(
            exists().where(
                SeriesCredit.series_id == Series.id,
                SeriesCredit.role == "artist",
                SeriesCredit.name == f.artist,
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
    if f.read_state == "unread":
        conds.append(agg.unread_count > 0)
    elif f.read_state == "read":
        conds.append(agg.unread_count == 0)
    elif f.read_state == "in_progress":
        conds.append(agg.unread_count > 0)
        conds.append(exists().where(ReadingProgress.series_id == Series.id))
    return conds


def list_series(
    session: Session,
    filters: SeriesFilters,
    *,
    cursor: str | None = None,
    limit: int = 24,
) -> tuple[list[SeriesRow], str | None]:
    """Return one page of grid rows and the cursor for the next page (or None)."""
    agg = _aggregates()
    stmt = (
        select(
            Series,
            agg.chapter_count.label("chapter_count"),
            agg.unread_count.label("unread_count"),
            agg.last_read.label("last_read"),
        )
        .where(*_conditions(filters, agg))
        .options(selectinload(Series.tags), selectinload(Series.credits))
    )

    order_expr, descending = _sort_expr(filters.sort, agg)
    if cursor is not None:
        data = decode_cursor(cursor)
        value: Any = data["v"]
        last_id: str = data["id"]
        if filters.sort in _TIME_SORTS and isinstance(value, str):
            value = datetime.fromisoformat(value)
        after = (
            or_(order_expr < value, and_(order_expr == value, Series.id < last_id))
            if descending
            else or_(order_expr > value, and_(order_expr == value, Series.id > last_id))
        )
        stmt = stmt.where(after)

    stmt = stmt.order_by(
        order_expr.desc() if descending else order_expr.asc(),
        Series.id.desc() if descending else Series.id.asc(),
    ).limit(limit + 1)

    rows = [
        SeriesRow(series=r[0], chapter_count=r[1], unread_count=r[2], last_read=r[3])
        for r in session.execute(stmt).all()
    ]

    next_cursor: str | None = None
    if len(rows) > limit:
        rows = rows[:limit]
        last = rows[-1]
        next_cursor = encode_cursor({"v": _sort_value(filters.sort, last), "id": last.series.id})
    return rows, next_cursor


def get_series(session: Session, series_id: str) -> SeriesRow | None:
    """Fetch a single series with its derived counts, or None."""
    agg = _aggregates()
    stmt = (
        select(
            Series,
            agg.chapter_count.label("chapter_count"),
            agg.unread_count.label("unread_count"),
            agg.last_read.label("last_read"),
        )
        .where(Series.id == series_id)
        .options(selectinload(Series.tags), selectinload(Series.credits))
    )
    row = session.execute(stmt).first()
    if row is None:
        return None
    return SeriesRow(series=row[0], chapter_count=row[1], unread_count=row[2], last_read=row[3])
