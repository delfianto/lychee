"""MangaDex OAuth2 personal-client flow.

MangaDex auth is Keycloak (OpenID Connect). A personal client gives a
``client_id`` / ``client_secret``; the ``password`` grant exchanges the user's
credentials for access + refresh tokens, and the ``refresh_token`` grant renews
them (tokens rotate, so callers must persist the new refresh token). The httpx
client is injectable so tests drive it with a mock transport.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from src.providers.mangadex_client import USER_AGENT

AUTH_URL = "https://auth.mangadex.org/realms/mangadex/protocol/openid-connect/token"


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str


def _client(client: httpx.Client | None) -> httpx.Client:
    return client or httpx.Client(timeout=30.0, headers={"User-Agent": USER_AGENT})


def _grant(client: httpx.Client | None, data: dict[str, str]) -> TokenPair:
    response = _client(client).post(AUTH_URL, data=data)
    _ = response.raise_for_status()
    body = response.json()
    return TokenPair(access_token=body["access_token"], refresh_token=body["refresh_token"])


def password_grant(
    *,
    client_id: str,
    client_secret: str,
    username: str,
    password: str,
    client: httpx.Client | None = None,
) -> TokenPair:
    return _grant(
        client,
        {
            "grant_type": "password",
            "client_id": client_id,
            "client_secret": client_secret,
            "username": username,
            "password": password,
        },
    )


def refresh_grant(
    *, client_id: str, client_secret: str, refresh_token: str, client: httpx.Client | None = None
) -> TokenPair:
    return _grant(
        client,
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
    )
