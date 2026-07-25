"""MangaUpdates tracker — password login (session token) + list updates.

MangaUpdates isn't OAuth: ``PUT /v1/account/login`` with username/password returns
a session token used as a Bearer. Progress is pushed by placing the series in the
right system list (reading=0 / wish=1 / complete=2 / unfinished=3 / hold=4) with a
chapter position via ``POST /v1/lists/series/update`` — the endpoint/shape used by
the Mihon (Tachiyomi) tracker. Best-effort, so it can't fail a read.
"""

from __future__ import annotations

import httpx

from src.trackers.base import TokenPair

API = "https://api.mangaupdates.com/v1"

# lychee library_status → MangaUpdates system list id.
_LIST_ID = {
    "reading": 0,
    "plan_to_read": 1,
    "completed": 2,
    "dropped": 3,
    "on_hold": 4,
    "re_reading": 0,
}


class MangaUpdatesTracker:
    id = "mangaupdates"
    external_id_key = "mu"
    auth_kind = "credentials"
    uses_pkce = False

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=10.0, headers={"User-Agent": "lychee/0.0.1"})

    def authorize_url(
        self, *, client_id: str, redirect_uri: str, state: str, code_challenge: str | None = None
    ) -> str:
        raise NotImplementedError("MangaUpdates uses username/password login")

    def exchange_code(
        self,
        *,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> TokenPair:
        raise NotImplementedError("MangaUpdates uses username/password login")

    def login(self, *, username: str, password: str) -> TokenPair:
        response = self._client.put(
            f"{API}/account/login", json={"username": username, "password": password}
        )
        _ = response.raise_for_status()
        return TokenPair(access_token=response.json()["context"]["session_token"])

    def account_name(self, access_token: str) -> str | None:
        response = self._client.get(
            f"{API}/account/profile", headers={"Authorization": f"Bearer {access_token}"}
        )
        _ = response.raise_for_status()
        return response.json().get("username")

    def push(self, *, access_token: str, media_id: str, status: str, progress: int) -> None:
        response = self._client.post(
            f"{API}/lists/series/update",
            json=[
                {
                    "series": {"id": int(media_id)},
                    "list_id": _LIST_ID.get(status, 0),
                    "status": {"chapter": progress},
                }
            ],
            headers={"Authorization": f"Bearer {access_token}"},
        )
        _ = response.raise_for_status()
