"""Integrations services: providers, trackers, sync state, about (ADR 13, 16)."""

from __future__ import annotations

import platform
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.metadata import apply_metadata
from src.catalog.models import Library, Series
from src.core.crypto import decrypt, encrypt
from src.core.exceptions import BadRequestError, NotFoundError
from src.downloads.provider import SeriesMetadata
from src.integrations.models import Provider, SyncState, Tracker
from src.integrations.schema import (
    AboutOut,
    ProviderConnect,
    ProviderOut,
    ProviderUpdate,
    SyncOut,
    TrackerOut,
    TrackerUpdate,
)
from src.integrations.seed import SYNC_STATE_ID
from src.providers.mangadex import MangaDexProvider
from src.providers.mangadex_auth import password_grant, refresh_grant
from src.providers.mangadex_client import API_BASE, USER_AGENT
from src.tasks.queue import Work, queue
from src.tasks.schema import TaskOut

_STARTED = datetime.now(UTC)
_MANGADEX = "mangadex"
_MANGADEX_LIBRARY = "MangaDex"
# MangaDex reading statuses that map 1:1 onto Series.library_status.
_READING_STATUSES = {"reading", "on_hold", "plan_to_read", "dropped", "re_reading", "completed"}


def _provider_out(p: Provider) -> ProviderOut:
    return ProviderOut(
        id=p.id,
        name=p.name,
        enabled=p.enabled,
        language=p.language,
        auto_match=p.auto_match,
        fetch_covers=p.fetch_covers,
        data_saver=p.data_saver,
        connected=bool(p.client_id and p.refresh_token_enc),
        account_name=p.account_name,
    )


def list_providers(session: Session) -> list[ProviderOut]:
    return [_provider_out(p) for p in session.scalars(select(Provider).order_by(Provider.name))]


def update_provider(session: Session, provider_id: str, data: ProviderUpdate) -> ProviderOut:
    provider = session.get(Provider, provider_id)
    if provider is None:
        raise NotFoundError(f"provider {provider_id!r} not found")
    if data.enabled is not None:
        provider.enabled = data.enabled
    if data.language is not None:
        provider.language = data.language
    if data.auto_match is not None:
        provider.auto_match = data.auto_match
    if data.fetch_covers is not None:
        provider.fetch_covers = data.fetch_covers
    if data.data_saver is not None:
        provider.data_saver = data.data_saver
    session.commit()
    return _provider_out(provider)


# --- MangaDex account: OAuth connect + follows import (PART F/M4) --------------


def _get_provider(session: Session, provider_id: str) -> Provider:
    provider = session.get(Provider, provider_id)
    if provider is None:
        raise NotFoundError(f"provider {provider_id!r} not found")
    return provider


def connect_provider(session: Session, provider_id: str, data: ProviderConnect) -> ProviderOut:
    """Exchange personal-client credentials for tokens; store the secret + refresh token encrypted."""
    provider = _get_provider(session, provider_id)
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
    return _provider_out(provider)


def disconnect_provider(session: Session, provider_id: str) -> ProviderOut:
    provider = _get_provider(session, provider_id)
    provider.client_id = None
    provider.client_secret_enc = None
    provider.refresh_token_enc = None
    provider.account_name = None
    session.commit()
    return _provider_out(provider)


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
        config = _get_provider(session, _MANGADEX)
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
    config = _get_provider(session, provider_id)
    if not (config.client_id and config.refresh_token_enc):
        raise BadRequestError("MangaDex account is not connected")
    task = queue.submit("import", "Importing MangaDex follows", _import_work())
    return TaskOut.model_validate(task)


def _tracker_out(t: Tracker) -> TrackerOut:
    return TrackerOut(
        id=t.id,
        name=t.name,
        connected=t.connected,
        sync_on_read=t.sync_on_read,
        account_name=t.account_name,
    )


def list_trackers(session: Session) -> list[TrackerOut]:
    return [_tracker_out(t) for t in session.scalars(select(Tracker).order_by(Tracker.name))]


def _get_tracker(session: Session, tracker_id: str) -> Tracker:
    tracker = session.get(Tracker, tracker_id)
    if tracker is None:
        raise NotFoundError(f"tracker {tracker_id!r} not found")
    return tracker


def update_tracker(session: Session, tracker_id: str, data: TrackerUpdate) -> TrackerOut:
    tracker = _get_tracker(session, tracker_id)
    if data.sync_on_read is not None:
        tracker.sync_on_read = data.sync_on_read
    session.commit()
    return _tracker_out(tracker)


def connect_tracker(session: Session, tracker_id: str) -> TrackerOut:
    """Stub OAuth connect (real flow is a follow-up): mark connected."""
    tracker = _get_tracker(session, tracker_id)
    tracker.connected = True
    tracker.account_name = tracker.account_name or "Connected account"
    session.commit()
    return _tracker_out(tracker)


def disconnect_tracker(session: Session, tracker_id: str) -> None:
    tracker = _get_tracker(session, tracker_id)
    tracker.connected = False
    tracker.account_name = None
    tracker.access_token = None
    tracker.refresh_token = None
    session.commit()


def _sync_state(session: Session) -> SyncState:
    state = session.get(SyncState, SYNC_STATE_ID)
    if state is None:
        state = SyncState(id=SYNC_STATE_ID)
        session.add(state)
        session.flush()
    return state


def _sync_out(state: SyncState) -> SyncOut:
    return SyncOut(
        last_sync=state.last_sync_at,
        auto_every_minutes=state.auto_every_minutes,
        new_chapters=state.new_chapters,
        syncing=state.syncing,
    )


def get_sync(session: Session) -> SyncOut:
    return _sync_out(_sync_state(session))


def run_sync(session: Session) -> SyncOut:
    """Stub sync (real MangaDex new-chapter check is B5): stamp last-sync now."""
    state = _sync_state(session)
    state.last_sync_at = datetime.now(UTC)
    state.syncing = False
    state.new_chapters = 0
    session.commit()
    return _sync_out(state)


def about() -> AboutOut:
    now = datetime.now(UTC)
    return AboutOut(
        version="0.0.1",
        platform=platform.platform(),
        database="SQLite",
        started=_STARTED,
        uptime_seconds=int((now - _STARTED).total_seconds()),
    )
