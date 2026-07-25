"""MangaUpdates tracker: password login + list update (mock transport)."""

import json

import httpx
from src.trackers.base import TokenPair
from src.trackers.mangaupdates import MangaUpdatesTracker


def test_login_returns_session_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PUT"
        assert request.url.path.endswith("/account/login")
        return httpx.Response(200, json={"context": {"session_token": "sess-1"}})

    tracker = MangaUpdatesTracker(client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert tracker.login(username="u", password="p") == TokenPair("sess-1")


def test_push_updates_list_with_chapter() -> None:
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["path"] = request.url.path
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json={})

    tracker = MangaUpdatesTracker(client=httpx.Client(transport=httpx.MockTransport(handler)))
    tracker.push(access_token="sess", media_id="777", status="completed", progress=9)

    assert captured["path"] == "/v1/lists/series/update"
    body = captured["body"]
    assert isinstance(body, list)
    assert body[0]["series"]["id"] == 777
    assert body[0]["list_id"] == 2  # completed → "complete" list
    assert body[0]["status"]["chapter"] == 9
