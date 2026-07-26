"""Collections (Lists) services — ordered groupings of series."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from src.catalog import repository as catalog_repo
from src.catalog.models import Series
from src.catalog.service import to_series_out
from src.collections.models import Collection, CollectionSeries
from src.collections.schema import (
    CollectionCreate,
    CollectionDetailOut,
    CollectionOut,
    CollectionUpdate,
)
from src.core.exceptions import NotFoundError


def _collection_kind(collection: Collection) -> str | None:
    """The member series' shared kind — "mixed" if they differ, ``None`` if empty."""
    kinds = {entry.series.kind for entry in collection.entries}
    if not kinds:
        return None
    if len(kinds) == 1:
        return next(iter(kinds))
    return "mixed"


def _to_out(collection: Collection) -> CollectionOut:
    return CollectionOut(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        series_ids=[entry.series_id for entry in collection.entries],
        kind=_collection_kind(collection),
    )


def _get(session: Session, collection_id: str) -> Collection:
    collection = session.get(Collection, collection_id)
    if collection is None:
        raise NotFoundError(f"collection {collection_id!r} not found")
    return collection


def list_collections(session: Session) -> list[CollectionOut]:
    collections = session.scalars(
        select(Collection)
        .order_by(Collection.created_at)
        .options(selectinload(Collection.entries).selectinload(CollectionSeries.series))
    ).all()
    return [_to_out(c) for c in collections]


def get_collection(session: Session, collection_id: str) -> CollectionDetailOut:
    collection = _get(session, collection_id)
    ids = [entry.series_id for entry in collection.entries]
    rows = catalog_repo.get_series_rows(session, ids)
    series = [to_series_out(rows[i]) for i in ids if i in rows]
    return CollectionDetailOut(
        id=collection.id, name=collection.name, description=collection.description, series=series
    )


def create_collection(session: Session, data: CollectionCreate) -> CollectionOut:
    collection = Collection(name=data.name, description=data.description)
    session.add(collection)
    session.commit()
    session.refresh(collection)
    return _to_out(collection)


def update_collection(
    session: Session, collection_id: str, data: CollectionUpdate
) -> CollectionOut:
    collection = _get(session, collection_id)
    if data.name is not None:
        collection.name = data.name
    if data.description is not None:
        collection.description = data.description
    session.commit()
    session.refresh(collection)
    return _to_out(collection)


def delete_collection(session: Session, collection_id: str) -> None:
    session.delete(_get(session, collection_id))
    session.commit()


def add_series(session: Session, collection_id: str, series_id: str) -> CollectionOut:
    collection = _get(session, collection_id)
    if session.get(Series, series_id) is None:
        raise NotFoundError(f"series {series_id!r} not found")
    exists = session.scalar(
        select(CollectionSeries).where(
            CollectionSeries.collection_id == collection_id,
            CollectionSeries.series_id == series_id,
        )
    )
    if exists is None:
        next_pos = (
            session.scalar(
                select(func.max(CollectionSeries.position)).where(
                    CollectionSeries.collection_id == collection_id
                )
            )
            or 0
        ) + 1
        session.add(
            CollectionSeries(collection_id=collection_id, series_id=series_id, position=next_pos)
        )
        session.commit()
    session.refresh(collection)
    return _to_out(collection)


def remove_series(session: Session, collection_id: str, series_id: str) -> CollectionOut:
    collection = _get(session, collection_id)
    entry = session.scalar(
        select(CollectionSeries).where(
            CollectionSeries.collection_id == collection_id,
            CollectionSeries.series_id == series_id,
        )
    )
    if entry is not None:
        session.delete(entry)
        session.commit()
    session.refresh(collection)
    return _to_out(collection)
