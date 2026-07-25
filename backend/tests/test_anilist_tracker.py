"""AniList tracker: authorize URL + code exchange + viewer lookup + push (mock transport)."""

import json
from typing import Any

import httpx
from src.trackers.anilist import AUTHORIZE_URL, AniListTracker
from src.trackers.base import TokenPair


def test_authorize_url_has_oauth_params() -> None:
    url = AniListTracker().authorize_url(
        client_id="cid", redirect_uri="http://localhost/cb", state="anilist"
    )
    assert url.startswith(AUTHORIZE_URL)
    assert "client_id=cid" in url
    assert "response_type=code" in url
    assert "state=anilist" in url


def test_exchange_code_and_account_name() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            return httpx.Response(200, json={"access_token": "tok", "refresh_token": "r"})
        return httpx.Response(200, json={"data": {"Viewer": {"name": "AniUser"}}})

    tracker = AniListTracker(client=httpx.Client(transport=httpx.MockTransport(handler)))
    pair = tracker.exchange_code(
        code="c", client_id="cid", client_secret="sec", redirect_uri="http://cb"
    )
    assert pair == TokenPair("tok", "r")
    assert tracker.account_name("tok") == "AniUser"


def test_push_maps_status_and_sends_variables() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={"data": {"SaveMediaListEntry": {"id": 1}}})

    tracker = AniListTracker(client=httpx.Client(transport=httpx.MockTransport(handler)))
    tracker.push(access_token="tok", media_id="42", status="completed", progress=7)

    assert captured["body"]["variables"] == {"mediaId": 42, "status": "COMPLETED", "progress": 7}
