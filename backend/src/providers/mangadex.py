"""MangaDex provider (ADR 13) — chapter listing + page download over the public API.

- ``list_chapters``: ``GET /manga/{id}/feed`` (paged), one entry per chapter number
  (first translation group wins), filtered to the requested language.
- ``fetch_pages``: ``GET /at-home/server/{chapterId}`` then download each page from
  ``{baseUrl}/data/{hash}/{filename}``.

The httpx client is injectable so tests can drive it with a mock transport.
"""

from __future__ import annotations

import httpx

from src.downloads.provider import RemoteChapter

API_BASE = "https://api.mangadex.org"
_PAGE_LIMIT = 100


def _volume(value: str | None) -> int | None:
    return int(value) if value and value.isdigit() else None


class MangaDexProvider:
    id = "mangadex"

    def __init__(self, client: httpx.Client | None = None) -> None:
        self._client = client or httpx.Client(
            base_url=API_BASE, timeout=30.0, headers={"User-Agent": "lychee/0.0.1"}
        )

    def list_chapters(self, provider_series_id: str, *, language: str = "en") -> list[RemoteChapter]:
        seen: set[str] = set()
        chapters: list[RemoteChapter] = []
        offset = 0
        while True:
            response = self._client.get(
                f"/manga/{provider_series_id}/feed",
                params={
                    "translatedLanguage[]": language,
                    "order[chapter]": "asc",
                    "limit": _PAGE_LIMIT,
                    "offset": offset,
                },
            )
            _ = response.raise_for_status()
            body = response.json()
            for item in body.get("data", []):
                attributes = item.get("attributes", {})
                number = attributes.get("chapter")
                if not number or number in seen:
                    continue
                seen.add(number)
                chapters.append(
                    RemoteChapter(
                        provider_chapter_id=item["id"],
                        number=number,
                        volume=_volume(attributes.get("volume")),
                        title=attributes.get("title") or None,
                        language=attributes.get("translatedLanguage", language),
                    )
                )
            offset += _PAGE_LIMIT
            if offset >= int(body.get("total", 0)):
                break
        return chapters

    def fetch_pages(self, chapter: RemoteChapter) -> list[bytes]:
        response = self._client.get(f"/at-home/server/{chapter.provider_chapter_id}")
        _ = response.raise_for_status()
        body = response.json()
        base_url = body["baseUrl"]
        chapter_hash = body["chapter"]["hash"]
        pages: list[bytes] = []
        for filename in body["chapter"]["data"]:
            page = self._client.get(f"{base_url}/data/{chapter_hash}/{filename}")
            _ = page.raise_for_status()
            pages.append(page.content)
        return pages
