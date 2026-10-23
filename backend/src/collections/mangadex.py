"""MDList import, discovery, feeds and owner-checked write-through operations."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
from urllib.parse import urlparse
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.models import Series
from src.collections.models import Collection
from src.collections.schema import CollectionCreate, CollectionUpdate, ListChapterOut, RemoteListOut
from src.collections.sync import apply_list, reconcile_account_flags
from src.core.exceptions import BadRequestError, ConflictError, LycheeError, NotFoundError
from src.core.schema import OffsetPage
from src.downloads.provider import CustomList
from src.integrations.models import Provider
from src.providers import mangadex_account as account
from src.providers.mangadex import MangaDexProvider
from src.providers.mangadex_client import API_BASE, USER_AGENT
from src.providers.mangadex_lists import LIST_LOCK
from src.tasks.queue import queue
from src.tasks.schema import TaskOut


class MangaDexError(LycheeError):
    status_code = 502
    code = "mangadex_error"


def reference_id(reference: str, kind: str = "list") -> str:
    value = reference.strip()
    if "://" in value:
        parsed = urlparse(value)
        parts = parsed.path.strip("/").split("/")
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"mangadex.org", "www.mangadex.org"}
            or len(parts) < 2
            or parts[0] != kind
        ):
            raise BadRequestError(f"Use a MangaDex {kind} URL or UUID")
        value = parts[1]
    try:
        return str(UUID(value))
    except ValueError as exc:
        raise BadRequestError(f"Invalid MangaDex {kind} ID") from exc


@contextmanager
def provider_session(session: Session, *, require_auth: bool = False) -> Iterator[MangaDexProvider]:
    config = session.get(Provider, "mangadex")
    connected = bool(
        config and config.client_id and config.client_secret_enc and config.refresh_token_enc
    )
    if require_auth and not connected:
        raise BadRequestError("Connect your MangaDex account in Settings first")
    headers = {"User-Agent": USER_AGENT}
    try:
        if connected and config is not None:
            headers["Authorization"] = f"Bearer {account._access_token(session, config)}"
        with httpx.Client(base_url=API_BASE, timeout=30, headers=headers) as client:
            yield MangaDexProvider(client=client)
    except httpx.HTTPStatusError as exc:
        status = exc.response.status_code
        if status == 404:
            raise NotFoundError("MangaDex list not found or not accessible") from exc
        if status == 409:
            raise ConflictError("The MangaDex list changed; sync it and retry") from exc
        if status in {401, 403}:
            raise BadRequestError(
                "MangaDex denied access; check your account and list ownership"
            ) from exc
        raise MangaDexError(f"MangaDex returned HTTP {status}; try again later") from exc
    except httpx.RequestError as exc:
        raise MangaDexError("Could not reach MangaDex; try again later") from exc


def _snapshot(session: Session, provider: MangaDexProvider, list_id: str) -> CustomList:
    custom = provider.lists.get(list_id)
    if account.is_connected(session):
        owned = custom.owner_id == provider.lists.user_id()
        followed = any(item.provider_list_id == list_id for item in provider.list_followed_lists())
        custom = replace(custom, owned=owned, followed=followed)
    return custom


def _owner(provider: MangaDexProvider, list_id: str) -> CustomList:
    custom = provider.lists.get(list_id)
    if not custom.owner_id or custom.owner_id != provider.lists.user_id():
        raise BadRequestError("Only the MangaDex list owner can edit or delete this list")
    return replace(custom, owned=True)


def _hydrate(session: Session, provider: MangaDexProvider, custom: CustomList) -> Collection:
    config = session.get(Provider, "mangadex")
    language = config.language if config else "en"
    rows = session.scalars(
        select(Series).where(
            Series.provider == "mangadex", Series.provider_series_id.in_(custom.manga_ids)
        )
    ).all()
    known = {row.provider_series_id: row for row in rows if row.provider_series_id}
    library = account._mangadex_library(session)
    for manga_id in dict.fromkeys(custom.manga_ids):
        if manga_id not in known:
            meta = provider.get_metadata(manga_id, language=language)
            known[manga_id] = account._upsert_series(
                session, library, meta, None, fetch_covers=bool(config and config.fetch_covers)
            )
    return apply_list(session, custom, known)


def enqueue_import(reference: str) -> TaskOut:
    list_id = reference_id(reference)

    def work(session: Session, progress):
        with LIST_LOCK, provider_session(session) as provider:
            progress(5, "Fetching MangaDex list")
            collection = _hydrate(session, provider, _snapshot(session, provider, list_id))
            session.commit()
            return {"collectionId": collection.id}

    return queue.submit_task("mdlist", "Importing MangaDex list", work)


def enqueue_sync(session: Session, collection_id: str) -> TaskOut:
    collection = session.get(Collection, collection_id)
    if collection is None:
        raise NotFoundError("List not found")
    if collection.provider != "mangadex" or not collection.provider_list_id:
        raise BadRequestError("This is a local list")
    return enqueue_import(collection.provider_list_id)


def enqueue_account_lists() -> TaskOut:
    def work(session: Session, progress):
        with LIST_LOCK, provider_session(session, require_auth=True) as provider:
            owned = provider.list_custom_lists()
            followed = provider.list_followed_lists()
            lists = {item.provider_list_id: item for item in followed}
            lists.update({item.provider_list_id: item for item in owned})
            reconcile_account_flags(session, list(lists.values()))
            for index, custom in enumerate(lists.values()):
                _hydrate(session, provider, custom)
                session.commit()
                progress(round((index + 1) / max(len(lists), 1) * 100), custom.name)
            return {"lists": len(lists)}

    return queue.submit_task("mdlist", "Syncing MangaDex lists", work)


def browse_user(session: Session, reference: str) -> list[RemoteListOut]:
    user_id = reference_id(reference, "user")
    with provider_session(session) as provider:
        return [
            RemoteListOut(
                id=item.provider_list_id,
                name=item.name,
                visibility=item.visibility,
                manga_count=len(item.manga_ids),
                source_url=f"https://mangadex.org/list/{item.provider_list_id}",
            )
            for item in provider.lists.listing(f"/user/{user_id}/list")
        ]


def create_remote(session: Session, data: CollectionCreate) -> Collection:
    with LIST_LOCK, provider_session(session, require_auth=True) as provider:
        custom = provider.lists.create(data.name.strip(), data.visibility)
        collection = apply_list(session, custom, {})
        collection.description = data.description
        return collection


def update_remote(session: Session, collection: Collection, data: CollectionUpdate) -> None:
    with LIST_LOCK, provider_session(session, require_auth=True) as provider:
        custom = _owner(provider, collection.provider_list_id or "")
        updated = provider.lists.update(custom, name=data.name, visibility=data.visibility)
        collection.name = updated.name
        collection.visibility = updated.visibility
        collection.provider_version = updated.version
        collection.owned = True


def delete_remote(session: Session, collection: Collection) -> None:
    with LIST_LOCK, provider_session(session, require_auth=True) as provider:
        custom = _owner(provider, collection.provider_list_id or "")
        provider.lists.delete(custom.provider_list_id)


def write_membership(
    session: Session, collection: Collection, series: Series, *, add: bool
) -> None:
    if series.provider != "mangadex" or not series.provider_series_id:
        raise BadRequestError("Match this series to MangaDex before adding it to an MDList")
    with LIST_LOCK, provider_session(session, require_auth=True) as provider:
        custom = _owner(provider, collection.provider_list_id or "")
        provider.lists.membership(custom.provider_list_id, series.provider_series_id, add=add)


def follow(session: Session, collection: Collection, followed: bool) -> None:
    with LIST_LOCK, provider_session(session, require_auth=True) as provider:
        list_id = collection.provider_list_id or ""
        custom = provider.lists.get(list_id)
        if custom.owner_id == provider.lists.user_id():
            raise BadRequestError("This is your own list")
        provider.lists.follow(list_id, followed=followed)
        collection.followed = followed
        collection.owned = False


def feed(
    session: Session, collection: Collection, *, page: int, page_size: int, language: str | None
) -> OffsetPage[ListChapterOut]:
    offset = (page - 1) * page_size
    if offset + page_size > 10000:
        raise BadRequestError("MangaDex feeds are limited to the first 10,000 chapters")
    config = session.get(Provider, "mangadex")
    language = language or (config.language if config else "en")
    with provider_session(session) as provider:
        body = provider.lists.feed(
            collection.provider_list_id or "", language=language, offset=offset, limit=page_size
        )
    items = []
    for chapter in body["data"]:
        attrs = chapter["attributes"]
        manga = next((r for r in chapter.get("relationships", []) if r["type"] == "manga"), None)
        if manga is None:
            continue
        local = session.scalar(
            select(Series).where(
                Series.provider == "mangadex", Series.provider_series_id == manga["id"]
            )
        )
        titles = manga.get("attributes", {}).get("title", {})
        title = (
            local.title
            if local
            else titles.get(language)
            or titles.get("en")
            or next(iter(titles.values()), manga["id"])
        )
        group = next(
            (
                r.get("attributes", {}).get("name")
                for r in chapter.get("relationships", [])
                if r["type"] == "scanlation_group"
            ),
            None,
        )
        published = attrs.get("publishAt")
        items.append(
            ListChapterOut(
                chapter_id=chapter["id"],
                manga_id=manga["id"],
                manga_title=title,
                series_id=local.id if local else None,
                number=attrs.get("chapter"),
                title=attrs.get("title"),
                language=attrs.get("translatedLanguage", language),
                group=group,
                uploaded_at=datetime.fromisoformat(published.replace("Z", "+00:00"))
                if published
                else None,
                source_url=f"https://mangadex.org/chapter/{chapter['id']}",
            )
        )
    return OffsetPage(items=items, total=body["total"], page=page, page_size=page_size)
