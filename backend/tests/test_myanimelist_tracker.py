"""MyAnimeList tracker: PKCE authorize + code exchange + list update (mock transport)."""

import httpx
from src.trackers.base import TokenPair
from src.trackers.myanimelist import AUTHORIZE_URL, MyAnimeListTracker


def test_authorize_url_includes_plain_pkce_challenge() -> None:
    url = MyAnimeListTracker().authorize_url(
        client_id="cid", redirect_uri="http://cb", state="myanimelist", code_challenge="verif"
    )
    assert url.startswith(AUTHORIZE_URL)
    assert "code_challenge=verif" in url
    assert "code_challenge_method=plain" in url


def test_exchange_code_sends_verifier_and_reads_name() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/token"):
            captured["token"] = request.content.decode()
            return httpx.Response(200, json={"access_token": "acc", "refresh_token": "ref"})
        return httpx.Response(200, json={"name": "MalUser"})

    tracker = MyAnimeListTracker(client=httpx.Client(transport=httpx.MockTransport(handler)))
    pair = tracker.exchange_code(
        code="c",
        client_id="cid",
        client_secret="sec",
        redirect_uri="http://cb",
        code_verifier="the-verifier",
    )
    assert pair == TokenPair("acc", "ref")
    assert "code_verifier=the-verifier" in captured["token"]
    assert tracker.account_name("acc") == "MalUser"


def test_push_patches_my_list_status() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["path"] = request.url.path
        captured["body"] = request.content.decode()
        return httpx.Response(200, json={})

    tracker = MyAnimeListTracker(client=httpx.Client(transport=httpx.MockTransport(handler)))
    tracker.push(access_token="acc", media_id="88", status="completed", progress=12)

    assert captured["method"] == "PATCH"
    assert captured["path"] == "/v2/manga/88/my_list_status"
    assert "status=completed" in captured["body"]
    assert "num_chapters_read=12" in captured["body"]
