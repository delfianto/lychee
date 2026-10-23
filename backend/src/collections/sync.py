"""Apply complete provider list snapshots without affecting the manga themselves."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.models import Series
from src.collections.models import Collection, CollectionSeries
from src.core.persistence.base_model import utc_now
from src.downloads.provider import CustomList


def apply_list(session: Session, custom: CustomList, series_by_id: dict[str, Series]) -> Collection:
    collection = session.scalar(
        select(Collection).where(
            Collection.provider == "mangadex",
            Collection.provider_list_id == custom.provider_list_id,
        )
    )
    if collection is None:
        collection = Collection(
            name=custom.name, provider="mangadex", provider_list_id=custom.provider_list_id
        )
        session.add(collection)
        session.flush()
    collection.name = custom.name
    collection.provider_owner_id = custom.owner_id
    collection.visibility = custom.visibility
    collection.provider_version = custom.version
    collection.owned = custom.owned
    collection.followed = custom.followed
    collection.last_synced_at = utc_now()
    ordered = list(dict.fromkeys(series_by_id[mid].id for mid in custom.manga_ids))
    have = {entry.series_id: entry for entry in collection.entries}
    for series_id, entry in have.items():
        if series_id not in ordered:
            collection.entries.remove(entry)
    for position, series_id in enumerate(ordered):
        if series_id in have:
            have[series_id].position = position
        else:
            collection.entries.append(CollectionSeries(series_id=series_id, position=position))
    return collection


def reconcile_account_flags(session: Session, lists: list[CustomList]) -> None:
    """Keep copies when a remote list is unfollowed/deleted, but stop claiming ownership/following."""
    owned = {item.provider_list_id for item in lists if item.owned}
    followed = {item.provider_list_id for item in lists if item.followed}
    for collection in session.scalars(select(Collection).where(Collection.provider == "mangadex")):
        if collection.provider_list_id not in owned:
            collection.owned = False
        if collection.provider_list_id not in followed:
            collection.followed = False
