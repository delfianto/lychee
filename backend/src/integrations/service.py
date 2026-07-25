"""Integrations services: providers, trackers, sync state, about (ADR 13, 16)."""

from __future__ import annotations

import platform
import secrets
from collections.abc import Callable
from datetime import UTC, datetime

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.catalog.metadata import apply_metadata
from src.catalog.models import Chapter, Library, Series
from src.core.crypto import decrypt, encrypt
from src.core.exceptions import BadRequestError, NotFoundError
from src.core.logging import get_logger
from src.downloads.provider import SeriesMetadata, get_provider
from src.integrations.models import Provider, SyncState, Tracker
from src.integrations.schema import (
    AboutOut,
    ProviderConnect,
    ProviderOut,
    ProviderUpdate,
    SyncOut,
    TrackerAuthUrl,
    TrackerCallback,
    TrackerConnect,
    TrackerOut,
    TrackerUpdate,
)
from src.integrations.seed import SYNC_STATE_ID
from src.providers.mangadex import MangaDexProvider
from src.providers.mangadex_auth import password_grant, refresh_grant
from src.providers.mangadex_client import API_BASE, USER_AGENT
from src.tasks.queue import Work, queue
from src.tasks.schema import TaskOut
from src.trackers.base import get_tracker

logger = get_logger(__name__)
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


def begin_tracker_connect(
    session: Session, tracker_id: str, data: TrackerConnect
) -> TrackerAuthUrl:
    """Store the client app credentials (secret encrypted) and return the authorize URL."""
    row = _get_tracker(session, tracker_id)
    impl = get_tracker(tracker_id)
    if impl is None:
        raise BadRequestError(f"tracker {tracker_id!r} is not supported yet")
    row.client_id = data.client_id
    row.client_secret_enc = encrypt(data.client_secret)  # requires LYCHEE_SECRET_KEY
    challenge: str | None = None
    if impl.uses_pkce:
        row.pkce_verifier = secrets.token_urlsafe(64)[:128]  # PKCE "plain": challenge == verifier
        challenge = row.pkce_verifier
    session.commit()
    url = impl.authorize_url(
        client_id=data.client_id,
        redirect_uri=data.redirect_uri,
        state=tracker_id,
        code_challenge=challenge,
    )
    return TrackerAuthUrl(authorize_url=url)


def complete_tracker_connect(
    session: Session, tracker_id: str, data: TrackerCallback
) -> TrackerOut:
    """Exchange the authorization code for a token (stored encrypted) and mark connected."""
    row = _get_tracker(session, tracker_id)
    impl = get_tracker(tracker_id)
    if impl is None:
        raise BadRequestError(f"tracker {tracker_id!r} is not supported yet")
    if not (row.client_id and row.client_secret_enc):
        raise BadRequestError("start the connect flow first")
    tokens = impl.exchange_code(
        code=data.code,
        client_id=row.client_id,
        client_secret=decrypt(row.client_secret_enc),
        redirect_uri=data.redirect_uri,
        code_verifier=row.pkce_verifier,
    )
    row.access_token_enc = encrypt(tokens.access_token)
    row.refresh_token_enc = encrypt(tokens.refresh_token) if tokens.refresh_token else None
    row.account_name = impl.account_name(tokens.access_token)
    row.pkce_verifier = None  # one-time use
    row.connected = True
    session.commit()
    return _tracker_out(row)


def disconnect_tracker(session: Session, tracker_id: str) -> None:
    tracker = _get_tracker(session, tracker_id)
    tracker.connected = False
    tracker.account_name = None
    tracker.client_id = None
    tracker.client_secret_enc = None
    tracker.access_token_enc = None
    tracker.refresh_token_enc = None
    tracker.pkce_verifier = None
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


def _sync_work() -> Work:
    def work(session: Session, on_progress: Callable[[int, str], None]) -> dict[str, int]:
        config = session.get(Provider, _MANGADEX)
        language = config.language if config else "en"
        matched = list(
            session.scalars(
                select(Series).where(
                    Series.provider.is_not(None), Series.provider_series_id.is_not(None)
                )
            )
        )
        total_new = 0
        for index, series in enumerate(matched, start=1):
            provider = get_provider(series.provider or "")
            if provider is not None:
                try:
                    remote = provider.list_chapters(series.provider_series_id or "", language=language)
                    local = set(
                        session.scalars(select(Chapter.number).where(Chapter.series_id == series.id))
                    )
                    series.available_chapters = sum(1 for r in remote if r.number not in local)
                    total_new += series.available_chapters
                except Exception as exc:  # noqa: BLE001 - per-series best-effort
                    logger.warning("sync_series_failed", series=series.title, error=str(exc))
            on_progress(round(index / len(matched) * 100) if matched else 100, series.title)
        state = _sync_state(session)
        state.new_chapters = total_new
        state.last_sync_at = datetime.now(UTC)
        state.syncing = False
        return {"newChapters": total_new}

    return work


def run_sync(session: Session) -> TaskOut:
    """Check every matched series for new remote chapters on the background queue."""
    task = queue.submit("sync", "Checking for new chapters", _sync_work())
    return TaskOut.model_validate(task)


def about() -> AboutOut:
    now = datetime.now(UTC)
    return AboutOut(
        version="0.0.1",
        platform=platform.platform(),
        database="SQLite",
        started=_STARTED,
        uptime_seconds=int((now - _STARTED).total_seconds()),
    )
