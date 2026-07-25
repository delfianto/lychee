"""MangaDex provider tests (httpx mock transport — no network)."""

import httpx
from src.downloads.provider import RemoteChapter
from src.providers.mangadex import MangaDexProvider
from src.providers.mangadex_client import API_BASE


def _handler(request: httpx.Request) -> httpx.Response:
    path = request.url.path
    if path == "/report":  # mandatory MangaDex@Home report (best-effort)
        return httpx.Response(200)
    if path.endswith("/feed"):
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "id": "c1",
                        "attributes": {
                            "chapter": "1",
                            "volume": "1",
                            "title": "One",
                            "translatedLanguage": "en",
                            "publishAt": "2021-01-02T00:00:00+00:00",
                        },
                        "relationships": [
                            {"type": "scanlation_group", "attributes": {"name": "Group X"}}
                        ],
                    },
                    # duplicate number from another group — should be de-duped
                    {"id": "c1b", "attributes": {"chapter": "1", "translatedLanguage": "en"}},
                    {
                        "id": "c2",
                        "attributes": {"chapter": "2", "volume": None, "translatedLanguage": "en"},
                    },
                ],
                "total": 3,
            },
        )
    if "/at-home/server/" in path:
        return httpx.Response(
            200,
            json={
                "baseUrl": "https://uploads.example",
                "chapter": {"hash": "h", "data": ["p1.png", "p2.png"], "dataSaver": ["s1.jpg", "s2.jpg"]},
            },
        )
    if path.startswith("/data-saver/"):
        return httpx.Response(200, content=b"SAVER")
    if path.startswith("/data/"):
        return httpx.Response(200, content=b"PAGE")
    return httpx.Response(404)


def _provider() -> MangaDexProvider:
    client = httpx.Client(base_url=API_BASE, transport=httpx.MockTransport(_handler))
    return MangaDexProvider(client=client)


def test_list_chapters_parses_dedupes_and_enriches() -> None:
    chapters = _provider().list_chapters("manga-1")
    assert [c.number for c in chapters] == ["1", "2"]
    assert (chapters[0].volume, chapters[0].title) == (1, "One")
    assert chapters[0].group_name == "Group X"
    assert chapters[0].published_at == "2021-01-02T00:00:00+00:00"
    assert chapters[1].volume is None


def test_fetch_pages_downloads_each() -> None:
    pages = _provider().fetch_pages(RemoteChapter("c1", "1", 1, None, "en"))
    assert pages == [b"PAGE", b"PAGE"]  # original quality from /data/


def test_fetch_pages_uses_data_saver_when_requested() -> None:
    pages = _provider().fetch_pages(RemoteChapter("c1", "1", 1, None, "en"), data_saver=True)
    assert pages == [b"SAVER", b"SAVER"]  # compressed quality from /data-saver/


def test_fetch_pages_reassigns_node_on_403() -> None:
    """An expired node (403) triggers a fresh /at-home/server lookup + retry."""
    state = {"athome": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/report":
            return httpx.Response(200)
        if "/at-home/server/" in path:
            state["athome"] += 1
            base = "https://dead.example" if state["athome"] == 1 else "https://live.example"
            return httpx.Response(200, json={"baseUrl": base, "chapter": {"hash": "h", "data": ["p1.png"]}})
        if request.url.host == "dead.example":
            return httpx.Response(403)  # node expired
        if request.url.host == "live.example":
            return httpx.Response(200, content=b"OK")
        return httpx.Response(404)

    provider = MangaDexProvider(
        client=httpx.Client(base_url=API_BASE, transport=httpx.MockTransport(handler))
    )
    pages = provider.fetch_pages(RemoteChapter("c1", "1", 1, None, "en"))
    assert pages == [b"OK"]
    assert state["athome"] == 2  # re-assigned a node after the 403
