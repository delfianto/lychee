"""Reading-tracker connections (AniList / MyAnimeList / MangaUpdates).

Manages each tracker's config row and its connect flow. OAuth trackers use a
two-step authorize → callback exchange (with PKCE when required); credentials
trackers use a one-step username/password login. Client secrets and tokens are
stored encrypted; the concrete auth/push logic lives in ``src/trackers/``.
"""

from __future__ import annotations

import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.core.crypto import decrypt, encrypt
from src.core.exceptions import BadRequestError, NotFoundError
from src.integrations.models import Tracker
from src.integrations.schema import (
    TrackerAuthUrl,
    TrackerCallback,
    TrackerConnect,
    TrackerLogin,
    TrackerOut,
    TrackerUpdate,
)
from src.trackers.base import get_tracker


def tracker_out(t: Tracker) -> TrackerOut:
    impl = get_tracker(t.id)
    return TrackerOut(
        id=t.id,
        name=t.name,
        connected=t.connected,
        sync_on_read=t.sync_on_read,
        account_name=t.account_name,
        auth_kind=impl.auth_kind if impl else "unsupported",
    )


def get_tracker_row(session: Session, tracker_id: str) -> Tracker:
    tracker = session.get(Tracker, tracker_id)
    if tracker is None:
        raise NotFoundError(f"tracker {tracker_id!r} not found")
    return tracker


def list_trackers(session: Session) -> list[TrackerOut]:
    return [tracker_out(t) for t in session.scalars(select(Tracker).order_by(Tracker.name))]


def update_tracker(session: Session, tracker_id: str, data: TrackerUpdate) -> TrackerOut:
    tracker = get_tracker_row(session, tracker_id)
    if data.sync_on_read is not None:
        tracker.sync_on_read = data.sync_on_read
    session.commit()
    return tracker_out(tracker)


def begin_connect(session: Session, tracker_id: str, data: TrackerConnect) -> TrackerAuthUrl:
    """Store the client app credentials (secret encrypted) and return the authorize URL."""
    row = get_tracker_row(session, tracker_id)
    impl = get_tracker(tracker_id)
    if impl is None:
        raise BadRequestError(f"tracker {tracker_id!r} is not supported yet")
    row.client_id = data.client_id
    row.client_secret_enc = encrypt(data.client_secret)  # requires LYCHEE_SECRET_KEY
    challenge: str | None = None
    if impl.uses_pkce:
        row.pkce_verifier = secrets.token_urlsafe(64)[:128]  # PKCE "plain": challenge == verifier
        challenge = row.pkce_verifier
    # Random per-attempt nonce, verified on callback — a fixed state (the tracker id) would let
    # a code obtained outside this flow (e.g. from a different browser/session) be redeemed here.
    state = secrets.token_urlsafe(32)
    row.state = state
    session.commit()
    url = impl.authorize_url(
        client_id=data.client_id,
        redirect_uri=data.redirect_uri,
        state=state,
        code_challenge=challenge,
    )
    return TrackerAuthUrl(authorize_url=url)


def complete_connect(session: Session, tracker_id: str, data: TrackerCallback) -> TrackerOut:
    """Exchange the authorization code for a token (stored encrypted) and mark connected."""
    row = get_tracker_row(session, tracker_id)
    impl = get_tracker(tracker_id)
    if impl is None:
        raise BadRequestError(f"tracker {tracker_id!r} is not supported yet")
    if not (row.client_id and row.client_secret_enc):
        raise BadRequestError("start the connect flow first")
    if not row.state or not secrets.compare_digest(data.state, row.state):
        raise BadRequestError("connect flow expired or was not started from this instance")
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
    row.state = None  # one-time use
    row.connected = True
    session.commit()
    return tracker_out(row)


def login(session: Session, tracker_id: str, data: TrackerLogin) -> TrackerOut:
    """Connect a credentials-based tracker (e.g. MangaUpdates) via username/password."""
    row = get_tracker_row(session, tracker_id)
    impl = get_tracker(tracker_id)
    if impl is None or impl.auth_kind != "credentials":
        raise BadRequestError(f"tracker {tracker_id!r} does not use password login")
    tokens = impl.login(username=data.username, password=data.password)
    row.access_token_enc = encrypt(tokens.access_token)  # requires LYCHEE_SECRET_KEY
    row.account_name = data.username
    row.connected = True
    session.commit()
    return tracker_out(row)


def disconnect(session: Session, tracker_id: str) -> None:
    tracker = get_tracker_row(session, tracker_id)
    tracker.connected = False
    tracker.account_name = None
    tracker.client_id = None
    tracker.client_secret_enc = None
    tracker.access_token_enc = None
    tracker.refresh_token_enc = None
    tracker.pkce_verifier = None
    session.commit()
