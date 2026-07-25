"""MangaDex account: OAuth connect/disconnect + follows / reading-status import.

Connecting exchanges a personal client's credentials for tokens (stored encrypted
on the provider config row). Importing refreshes the token, then pulls the user's
followed manga + reading statuses into a virtual "MangaDex" library, applying
provider metadata and mapping each status onto ``Series.library_status``.
"""

from __future__ import annotations

from collections.abc import Callable

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.metadata import apply_metadata
from src.catalog.models import Library, Series
from src.core.crypto import decrypt, encrypt
from src.core.exceptions import BadRequestError
from src.downloads.provider import SeriesMetadata
from src.integrations.providers import get_provider_row, provider_out
from src.integrations.schema import ProviderConnect, ProviderOut
from src.providers.mangadex import MangaDexProvider
from src.providers.mangadex_auth import password_grant, refresh_grant
from src.providers.mangadex_client import API_BASE, USER_AGENT
from src.tasks.queue import Work, queue
from src.tasks.schema import TaskOut

_MANGADEX = "mangadex"
_MANGADEX_LIBRARY = "MangaDex"
# MangaDex reading statuses that map 1:1 onto Series.library_status.
_READING_STATUSES = {"reading", "on_hold", "plan_to_read", "dropped", "re_reading", "completed"}


def connect(session: Session, provider_id: str, data: ProviderConnect) -> ProviderOut:
    """Exchange personal-client credentials for tokens; store the secret + refresh token encrypted."""
    provider = get_provider_row(session, provider_id)
    tokens = password_grant(
        client_id=data.client_id,
        client_secret=data.client_secret,
        username=data.username,
        password=data.password,
    )
    provider.client_id = data.client_id
    provider.client_secret_enc = encrypt(data.client_secret)
    provider.refresh_token_enc = encrypt(tokens.refresh_token)
    provider.account_name = data.username
    session.commit()
    return provider_out(provider)


def disconnect(session: Session, provider_id: str) -> ProviderOut:
    provider = get_provider_row(session, provider_id)
    provider.client_id = None
    provider.client_secret_enc = None
    provider.refresh_token_enc = None
    provider.account_name = None
    session.commit()
    return provider_out(provider)


def _authed_provider(access_token: str) -> MangaDexProvider:
    client = httpx.Client(
        base_url=API_BASE,
        timeout=30.0,
        headers={"User-Agent": USER_AGENT, "Authorization": f"Bearer {access_token}"},
    )
    return MangaDexProvider(client=client)


def _mangadex_library(session: Session) -> Library:
    library = session.scalar(select(Library).where(Library.name == _MANGADEX_LIBRARY))
    if library is None:
        library = Library(name=_MANGADEX_LIBRARY, path="mangadex://follows", kind="mixed")
        session.add(library)
        session.flush()
    return library


def _upsert_followed_series(
    session: Session, library: Library, meta: SeriesMetadata, status: str | None, *, fetch_covers: bool
) -> None:
    series = session.scalar(
        select(Series).where(
            Series.provider == _MANGADEX, Series.provider_series_id == meta.provider_series_id
        )
    )
    if series is None:
        series = Series(
            library_id=library.id,
            kind="manga",
            title=meta.title,
            sort_title=meta.title.lower(),
            path_rel=meta.provider_series_id,
            provider=_MANGADEX,
            provider_series_id=meta.provider_series_id,
        )
        session.add(series)
        session.flush()
    apply_metadata(session, series, meta, fetch_covers=fetch_covers)
    if status in _READING_STATUSES:
        series.library_status = status


def _import_work() -> Work:
    def work(session: Session, on_progress: Callable[[int, str], None]) -> dict[str, int]:
        config = get_provider_row(session, _MANGADEX)
        if not (config.client_id and config.client_secret_enc and config.refresh_token_enc):
            raise BadRequestError("MangaDex account is not connected")
        # Tokens rotate on refresh — persist the new refresh token before the long import.
        tokens = refresh_grant(
            client_id=config.client_id,
            client_secret=decrypt(config.client_secret_enc),
            refresh_token=decrypt(config.refresh_token_enc),
        )
        config.refresh_token_enc = encrypt(tokens.refresh_token)
        session.commit()

        provider = _authed_provider(tokens.access_token)
        on_progress(10, "Fetching follows")
        follows = provider.list_follows(language=config.language)
        statuses = provider.reading_status()
        library = _mangadex_library(session)
        for index, meta in enumerate(follows, start=1):
            _upsert_followed_series(
                session, library, meta, statuses.get(meta.provider_series_id),
                fetch_covers=config.fetch_covers,
            )
            on_progress(round(index / len(follows) * 100) if follows else 100, meta.title)
        return {"imported": len(follows)}

    return work


def import_follows(session: Session, provider_id: str) -> TaskOut:
    """Validate the account is connected, then import follows + statuses on the queue."""
    config = get_provider_row(session, provider_id)
    if not (config.client_id and config.refresh_token_enc):
        raise BadRequestError("MangaDex account is not connected")
    task = queue.submit("import", "Importing MangaDex follows", _import_work())
    return TaskOut.model_validate(task)
