"""Default integration rows: the MangaDex provider, trackers, and sync singleton.

Idempotent — inserts each row only if its (slug) id is absent, preserving any
connection state / option toggles the user has changed.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.integrations.import_config import IMPORT_CONFIG_ID
from src.integrations.models import ImportConfig, Provider, SyncState, Tracker

SYNC_STATE_ID = "default"

_PROVIDERS = [("mangadex", "MangaDex")]
_TRACKERS = [
    ("anilist", "AniList"),
    ("myanimelist", "MyAnimeList"),
    ("mangaupdates", "MangaUpdates"),
    ("novelupdates", "NovelUpdates"),
]


def seed_integrations(session: Session) -> None:
    """Insert the default providers, trackers, and the sync-state singleton."""
    have_providers = set(session.scalars(select(Provider.id)).all())
    for pid, name in _PROVIDERS:
        if pid not in have_providers:
            session.add(Provider(id=pid, name=name))

    have_trackers = set(session.scalars(select(Tracker.id)).all())
    for tid, name in _TRACKERS:
        if tid not in have_trackers:
            session.add(Tracker(id=tid, name=name))

    if session.get(SyncState, SYNC_STATE_ID) is None:
        session.add(SyncState(id=SYNC_STATE_ID))

    if session.get(ImportConfig, IMPORT_CONFIG_ID) is None:
        session.add(ImportConfig(id=IMPORT_CONFIG_ID))
