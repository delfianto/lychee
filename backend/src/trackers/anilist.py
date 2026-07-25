"""AniList tracker — OAuth2 authorization-code + a GraphQL viewer lookup (PART F).

Connect flow: build ``authorize_url`` → the user authorises in-browser → AniList
redirects back with a ``code`` → ``exchange_code`` swaps it for an access token
(long-lived, ~1 year; AniList issues no refresh token). ``account_name`` confirms
the token via the GraphQL ``Viewer`` query. Outbound progress push (SaveMedia
ListEntry) is a follow-up. The httpx client is injectable for tests.
"""

from __future__ import annotations

from urllib.parse import urlencode

import httpx

from src.trackers.base import TokenPair

AUTHORIZE_URL = "https://anilist.co/api/v2/oauth/authorize"
TOKEN_URL = "https://anilist.co/api/v2/oauth/token"
GRAPHQL_URL = "https://graphql.anilist.co"

# lychee library_status → AniList MediaListStatus enum.
_STATUS = {
    "reading": "CURRENT",
    "completed": "COMPLETED",
    "on_hold": "PAUSED",
    "dropped": "DROPPED",
    "plan_to_read": "PLANNING",
    "re_reading": "REPEATING",
}
_SAVE_ENTRY = (
    "mutation($mediaId:Int,$status:MediaListStatus,$progress:Int){"
    "SaveMediaListEntry(mediaId:$mediaId,status:$status,progress:$progress){id}}"
)


class AniListTracker:
    id = "anilist"
    external_id_key = "al"  # Series.external_ids["al"] is the AniList media id
    uses_pkce = False

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(timeout=10.0, headers={"User-Agent": "lychee/0.0.1"})

    def authorize_url(
        self, *, client_id: str, redirect_uri: str, state: str, code_challenge: str | None = None
    ) -> str:
        query = urlencode(
            {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "state": state,
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
            json={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "code": code,
            },
        )
        _ = response.raise_for_status()
        body = response.json()
        return TokenPair(access_token=body["access_token"], refresh_token=body.get("refresh_token"))

    def account_name(self, access_token: str) -> str | None:
        response = self._client.post(
            GRAPHQL_URL,
            json={"query": "query { Viewer { name } }"},
            headers={"Authorization": f"Bearer {access_token}"},
        )
        _ = response.raise_for_status()
        viewer = response.json().get("data", {}).get("Viewer") or {}
        return viewer.get("name")

    def push(self, *, access_token: str, media_id: str, status: str, progress: int) -> None:
        response = self._client.post(
            GRAPHQL_URL,
            json={
                "query": _SAVE_ENTRY,
                "variables": {
                    "mediaId": int(media_id),
                    "status": _STATUS.get(status, "CURRENT"),
                    "progress": progress,
                },
            },
            headers={"Authorization": f"Bearer {access_token}"},
        )
        _ = response.raise_for_status()
