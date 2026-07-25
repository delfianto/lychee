"""Reading-tracker abstraction + registry (AniList / MyAnimeList / … ) — PART F.

A tracker connects via OAuth2 (authorization-code) and can later push read
progress. This module defines the contract + a registry; concrete trackers
(AniList first) register at startup. ``external_id_key`` is the ``Series.
external_ids`` key holding this tracker's media id (MangaDex M1 stored them).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str | None = None


class Tracker(Protocol):
    id: str
    external_id_key: str
    uses_pkce: bool  # MAL requires PKCE; the service generates a verifier when true

    def authorize_url(
        self, *, client_id: str, redirect_uri: str, state: str, code_challenge: str | None = None
    ) -> str: ...

    def exchange_code(
        self,
        *,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> TokenPair: ...

    def account_name(self, access_token: str) -> str | None: ...

    def push(self, *, access_token: str, media_id: str, status: str, progress: int) -> None:
        """Push read progress. ``status`` is a lychee library_status; the impl maps it."""
        ...


_REGISTRY: dict[str, Tracker] = {}


def register_tracker(tracker: Tracker) -> None:
    _REGISTRY[tracker.id] = tracker


def get_tracker(tracker_id: str) -> Tracker | None:
    return _REGISTRY.get(tracker_id)
