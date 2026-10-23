"""Collections (Lists) services — ordered groupings of series."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from src.catalog import repository as catalog_repo
from src.catalog.models import Series
from src.catalog.service import to_series_out
from src.collections import mangadex
from src.collections.models import Collection, CollectionSeries
from src.collections.schema import (
    CollectionCreate,
    CollectionDetailOut,
    CollectionOut,
    CollectionUpdate,
)
from src.core.exceptions import BadRequestError, NotFoundError
from src.providers.mangadex_lists import LIST_LOCK


def _collection_kind(collection: Collection) -> str | None:
    """The member series' shared kind — "mixed" if they differ, ``None`` if empty."""
    kinds = {entry.series.kind for entry in collection.entries}
    if not kinds:
        return None
    if len(kinds) == 1:
        return next(iter(kinds))
    return "mixed"


def _info(collection: Collection) -> dict:
    return {
        "id": collection.id,
        "name": collection.name,
        "description": collection.description,
        "provider": collection.provider,
        "provider_list_id": collection.provider_list_id,
        "source_url": f"https://mangadex.org/list/{collection.provider_list_id}"
        if collection.provider == "mangadex"
        else None,
        "visibility": collection.visibility,
        "owned": collection.owned,
        "followed": collection.followed,
        "editable": collection.provider is None or collection.owned,
        "last_synced_at": collection.last_synced_at,
    }


def _to_out(collection: Collection) -> CollectionOut:
    return CollectionOut(
        **_info(collection),
        series_ids=[entry.series_id for entry in collection.entries],
        kind=_collection_kind(collection),
    )


def _get(session: Session, collection_id: str) -> Collection:
    collection = session.get(Collection, collection_id)
    if collection is None:
        raise NotFoundError(f"collection {collection_id!r} not found")
    return collection


def _reloaded(session: Session, collection_id: str) -> Collection:
    """Re-fetch with the same eager-load as `list_collections`, for `_to_out` after a write.

    `session.refresh()` alone doesn't apply eager-load options, so `_to_out`'s
    `_collection_kind` (which walks `entry.series` per member) would otherwise
    lazy-load once per entry.
    """
    return session.scalars(
        select(Collection)
        .where(Collection.id == collection_id)
        .options(selectinload(Collection.entries).selectinload(CollectionSeries.series))
    ).one()


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
    return CollectionDetailOut(**_info(collection), series=series)


def create_collection(session: Session, data: CollectionCreate) -> CollectionOut:
    with LIST_LOCK:
        if not data.name.strip():
            raise BadRequestError("List name cannot be blank")
        collection = (
            mangadex.create_remote(session, data)
            if data.provider == "mangadex"
            else Collection(name=data.name.strip(), description=data.description)
        )
        session.add(collection)
        session.commit()
        return _to_out(_reloaded(session, collection.id))


def update_collection(
    session: Session, collection_id: str, data: CollectionUpdate
) -> CollectionOut:
    with LIST_LOCK:
        collection = _get(session, collection_id)
        if data.name is not None and not data.name.strip():
            raise BadRequestError("List name cannot be blank")
        if collection.provider == "mangadex":
            mangadex.update_remote(session, collection, data)
        elif data.visibility is not None:
            raise BadRequestError("Only MangaDex lists have visibility settings")
        if data.name is not None:
            collection.name = data.name
        if data.description is not None:
            collection.description = data.description
        session.commit()
        return _to_out(_reloaded(session, collection_id))


def delete_collection(session: Session, collection_id: str, *, remote: bool = False) -> None:
    with LIST_LOCK:
        collection = _get(session, collection_id)
        if remote:
            if collection.provider != "mangadex":
                raise BadRequestError("This is a local list")
            mangadex.delete_remote(session, collection)
        session.delete(collection)
        session.commit()


def add_series(session: Session, collection_id: str, series_id: str) -> CollectionOut:
    with LIST_LOCK:
        collection = _get(session, collection_id)
        series = session.get(Series, series_id)
        if series is None:
            raise NotFoundError(f"series {series_id!r} not found")
        exists = session.scalar(
            select(CollectionSeries).where(
                CollectionSeries.collection_id == collection_id,
                CollectionSeries.series_id == series_id,
            )
        )
        if collection.provider == "mangadex":
            mangadex.write_membership(session, collection, series, add=True)
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
                CollectionSeries(
                    collection_id=collection_id, series_id=series_id, position=next_pos
                )
            )
            session.commit()
        return _to_out(_reloaded(session, collection_id))


def remove_series(session: Session, collection_id: str, series_id: str) -> CollectionOut:
    with LIST_LOCK:
        collection = _get(session, collection_id)
        if collection.provider == "mangadex":
            series = session.get(Series, series_id)
            if series is None:
                raise NotFoundError("Series not found")
            mangadex.write_membership(session, collection, series, add=False)
        entry = session.scalar(
            select(CollectionSeries).where(
                CollectionSeries.collection_id == collection_id,
                CollectionSeries.series_id == series_id,
            )
        )
        if entry is not None:
            session.delete(entry)
            session.commit()
        return _to_out(_reloaded(session, collection_id))


def _provider_collection(session: Session, collection_id: str) -> Collection:
    collection = _get(session, collection_id)
    if collection.provider != "mangadex" or not collection.provider_list_id:
        raise BadRequestError("This is a local list")
    return collection


def follow_collection(session: Session, collection_id: str, followed: bool) -> CollectionOut:
    with LIST_LOCK:
        collection = _provider_collection(session, collection_id)
        mangadex.follow(session, collection, followed)
        session.commit()
        return _to_out(_reloaded(session, collection_id))


def collection_feed(
    session: Session, collection_id: str, *, page: int, page_size: int, language: str | None
):
    return mangadex.feed(
        session,
        _provider_collection(session, collection_id),
        page=page,
        page_size=page_size,
        language=language,
    )
