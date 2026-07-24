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
                        },
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
            json={"baseUrl": "https://uploads.example", "chapter": {"hash": "h", "data": ["p1.png", "p2.png"]}},
        )
    if path.startswith("/data/"):
        return httpx.Response(200, content=b"PAGE")
    return httpx.Response(404)


def _provider() -> MangaDexProvider:
    client = httpx.Client(base_url=API_BASE, transport=httpx.MockTransport(_handler))
    return MangaDexProvider(client=client)


def test_list_chapters_parses_and_dedupes() -> None:
    chapters = _provider().list_chapters("manga-1")
    assert [c.number for c in chapters] == ["1", "2"]
    assert (chapters[0].volume, chapters[0].title) == (1, "One")
    assert chapters[1].volume is None


def test_fetch_pages_downloads_each() -> None:
    pages = _provider().fetch_pages(RemoteChapter("c1", "1", 1, None, "en"))
    assert pages == [b"PAGE", b"PAGE"]
