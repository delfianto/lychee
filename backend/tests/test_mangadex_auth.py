"""MangaDex OAuth grants (mock transport — no network)."""

import httpx
from src.providers.mangadex_auth import TokenPair, password_grant, refresh_grant


def _handler(request: httpx.Request) -> httpx.Response:
    assert request.url.path.endswith("/token")  # posts to the Keycloak token endpoint
    return httpx.Response(200, json={"access_token": "acc", "refresh_token": "ref"})


def test_password_and_refresh_grants_parse_tokens() -> None:
    client = httpx.Client(transport=httpx.MockTransport(_handler))
    got = password_grant(client_id="c", client_secret="s", username="u", password="p", client=client)
    assert got == TokenPair("acc", "ref")

    renewed = refresh_grant(client_id="c", client_secret="s", refresh_token="r", client=client)
    assert renewed.refresh_token == "ref"
