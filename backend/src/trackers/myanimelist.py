"""MyAnimeList tracker — OAuth2 with PKCE + list updates (PART F).

MAL requires PKCE with ``code_challenge_method=plain`` (challenge == verifier), so
the service generates a verifier, passes it as the challenge in ``authorize_url``,
and hands it back to ``exchange_code``. Progress is pushed via
``PATCH /v2/manga/{id}/my_list_status`` (``status`` + ``num_chapters_read``). The
httpx client is injectable for tests.
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx

from src.trackers.base import TokenPair

AUTHORIZE_URL = "https://myanimelist.net/v1/oauth2/authorize"
TOKEN_URL = "https://myanimelist.net/v1/oauth2/token"
API_BASE = "https://api.myanimelist.net/v2"

# lychee library_status → MAL status (MAL has no "re_reading").
_STATUS = {
    "reading": "reading",
    "completed": "completed",
    "on_hold": "on_hold",
    "dropped": "dropped",
    "plan_to_read": "plan_to_read",
    "re_reading": "reading",
}


class MyAnimeListTracker:
    id = "myanimelist"
    external_id_key = "mal"
    auth_kind = "oauth"
    uses_pkce = True

    def login(self, *, username: str, password: str) -> TokenPair:
        raise NotImplementedError("MyAnimeList uses OAuth")

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=10.0, headers={"User-Agent": "lychee/0.0.1"})

    def authorize_url(
        self, *, client_id: str, redirect_uri: str, state: str, code_challenge: str | None = None
    ) -> str:
        query = urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "state": state,
                "code_challenge": code_challenge or "",
                "code_challenge_method": "plain",
            }
        )
        return f"{AUTHORIZE_URL}?{query}"

    def exchange_code(
        self,
        *,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        code_verifier: str | None = None,
    ) -> TokenPair:
        response = self._client.post(
            TOKEN_URL,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "code": code,
                "code_verifier": code_verifier or "",
                "redirect_uri": redirect_uri,
            },
        )
        _ = response.raise_for_status()
        body = response.json()
        return TokenPair(access_token=body["access_token"], refresh_token=body.get("refresh_token"))

    def account_name(self, access_token: str) -> str | None:
        response = self._client.get(
            f"{API_BASE}/users/@me", headers={"Authorization": f"Bearer {access_token}"}
        )
        _ = response.raise_for_status()
        return response.json().get("name")

    def push(self, *, access_token: str, media_id: str, status: str, progress: int) -> None:
        response = self._client.patch(
            f"{API_BASE}/manga/{int(media_id)}/my_list_status",
            data={"status": _STATUS.get(status, "reading"), "num_chapters_read": progress},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        _ = response.raise_for_status()
