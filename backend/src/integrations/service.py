"""Integrations services: providers, trackers, sync state, about (ADR 13, 16)."""

from __future__ import annotations

import platform
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.exceptions import NotFoundError
from src.integrations.models import Provider, SyncState, Tracker
from src.integrations.schema import (
    AboutOut,
    ProviderOut,
    ProviderUpdate,
    SyncOut,
    TrackerOut,
    TrackerUpdate,
)
from src.integrations.seed import SYNC_STATE_ID

_STARTED = datetime.now(UTC)


def _provider_out(p: Provider) -> ProviderOut:
    return ProviderOut(
        id=p.id,
        name=p.name,
        enabled=p.enabled,
        language=p.language,
        auto_match=p.auto_match,
        fetch_covers=p.fetch_covers,
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
    session.commit()
    return _provider_out(provider)


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
