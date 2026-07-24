"""MangaDex provider (ADR 13, PART F) — chapter listing + page download.

Runs over the rate-limited ``MangaDexClient`` (global 5 req/s + at-home 40/min,
429/retry handling, mandatory MangaDex@Home reporting). Metadata fetch, matching,
and sync (``search`` / ``get_metadata`` / ``list_new_chapters``) land in PART F
M1–M5; the ``MetadataProvider`` contract they satisfy lives in downloads/provider.
"""

from __future__ import annotations

import time

import httpx

from src.downloads.provider import RemoteChapter
from src.providers.mangadex_client import MangaDexClient

_PAGE_LIMIT = 100


def _volume(value: str | None) -> int | None:
    return int(value) if value and value.isdigit() else None


class MangaDexProvider:
    id = "mangadex"

    def __init__(
        self, client: httpx.Client | None = None, *, api: MangaDexClient | None = None
    ) -> None:
        # Accept a raw httpx.Client (tests inject a MockTransport) or a ready client.
        self._api = api or MangaDexClient(client=client)

    def list_chapters(self, provider_series_id: str, *, language: str = "en") -> list[RemoteChapter]:
        seen: set[str] = set()
        chapters: list[RemoteChapter] = []
        offset = 0
        while True:
            response = self._api.get(
                f"/manga/{provider_series_id}/feed",
                params={
                    "translatedLanguage[]": language,
                    "order[chapter]": "asc",
                    "limit": _PAGE_LIMIT,
                    "offset": offset,
                },
            )
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
        response = self._api.get(f"/at-home/server/{chapter.provider_chapter_id}", athome=True)
        body = response.json()
        base_url = body["baseUrl"]
        chapter_hash = body["chapter"]["hash"]
        pages: list[bytes] = []
        for filename in body["chapter"]["data"]:
            url = f"{base_url}/data/{chapter_hash}/{filename}"
            started = time.monotonic()
            try:
                page = self._api.get_bytes(url)
            except httpx.HTTPError:
                self._report(url, success=False, nbytes=0, started=started, cached=False)
                raise
            content = page.content
            cached = page.headers.get("X-Cache", "").upper().startswith("HIT")
            self._report(url, success=True, nbytes=len(content), started=started, cached=cached)
            pages.append(content)
        return pages

    def _report(self, url: str, *, success: bool, nbytes: int, started: float, cached: bool) -> None:
        self._api.report(
            url,
            success=success,
            nbytes=nbytes,
            duration_ms=int((time.monotonic() - started) * 1000),
            cached=cached,
        )
