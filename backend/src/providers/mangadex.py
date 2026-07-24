"""MangaDex provider (ADR 13, PART F) — chapter listing + page download.

Runs over the rate-limited ``MangaDexClient`` (global 5 req/s + at-home 40/min,
429/retry handling, mandatory MangaDex@Home reporting). Metadata fetch, matching,
and sync (``search`` / ``get_metadata`` / ``list_new_chapters``) land in PART F
M1–M5; the ``MetadataProvider`` contract they satisfy lives in downloads/provider.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from src.downloads.provider import MangaMatch, RemoteChapter, SeriesMetadata
from src.providers.mangadex_client import MangaDexClient

_CONTENT_RATINGS = ["safe", "suggestive", "erotica", "pornographic"]

_PAGE_LIMIT = 100
_COVERS_BASE = "https://uploads.mangadex.org/covers"
_TRACKER_LINKS = {"al", "mal", "mu", "ap", "kt", "nu"}  # links we keep for tracker matching


def _volume(value: str | None) -> int | None:
    return int(value) if value and value.isdigit() else None


def _localized(mapping: dict[str, str] | None, language: str) -> str | None:
    """Pick a value from a MangaDex LocalizedString: preferred language → en → any."""
    if not mapping:
        return None
    return mapping.get(language) or mapping.get("en") or next(iter(mapping.values()), None)


def _as_int(value: str | None) -> int | None:
    try:
        return int(float(value)) if value else None
    except (TypeError, ValueError):
        return None


def _relationship_names(relationships: list[dict[str, Any]], kind: str) -> list[str]:
    """Names of expanded ``kind`` relationships (needs includes[]=author/artist)."""
    return [
        rel["attributes"]["name"]
        for rel in relationships
        if rel.get("type") == kind and rel.get("attributes", {}).get("name")
    ]


def _relationship_attr(relationships: list[dict[str, Any]], kind: str, attr: str) -> str | None:
    for rel in relationships:
        if rel.get("type") == kind and rel.get("attributes"):
            return rel["attributes"].get(attr)
    return None


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

    def search(self, title: str, *, limit: int = 5) -> list[MangaMatch]:
        response = self._api.get(
            "/manga",
            params={
                "title": title,
                "limit": limit,
                "includes[]": ["cover_art"],
                "contentRating[]": _CONTENT_RATINGS,
                "order[relevance]": "desc",
            },
        )
        matches: list[MangaMatch] = []
        for data in response.json().get("data", []):
            attributes: dict[str, Any] = data.get("attributes", {})
            cover_file = _relationship_attr(data.get("relationships", []), "cover_art", "fileName")
            matches.append(
                MangaMatch(
                    provider_series_id=data["id"],
                    title=_localized(attributes.get("title"), "en") or data["id"],
                    year=attributes.get("year"),
                    status=attributes.get("status"),
                    cover_url=f"{_COVERS_BASE}/{data['id']}/{cover_file}.256.jpg" if cover_file else None,
                )
            )
        return matches

    def get_metadata(self, provider_series_id: str, *, language: str = "en") -> SeriesMetadata:
        response = self._api.get(
            f"/manga/{provider_series_id}",
            params={"includes[]": ["cover_art", "author", "artist"]},
        )
        data = response.json()["data"]
        attributes: dict[str, Any] = data.get("attributes", {})
        relationships: list[dict[str, Any]] = data.get("relationships", [])

        alt_titles = [
            (lang, value)
            for entry in attributes.get("altTitles", [])
            for lang, value in entry.items()
        ]
        tags = [
            (_localized(tag["attributes"].get("name"), language) or "", tag["attributes"].get("group", "genre"))
            for tag in attributes.get("tags", [])
            if tag.get("attributes")
        ]
        cover_file = _relationship_attr(relationships, "cover_art", "fileName")
        links: dict[str, str] = attributes.get("links") or {}

        return SeriesMetadata(
            provider_series_id=provider_series_id,
            title=_localized(attributes.get("title"), language) or provider_series_id,
            alt_titles=alt_titles,
            description=_localized(attributes.get("description"), language),
            status=attributes.get("status"),
            year=attributes.get("year"),
            content_rating=attributes.get("contentRating"),
            demographic=attributes.get("publicationDemographic"),
            original_language=attributes.get("originalLanguage"),
            tags=[(name, group) for name, group in tags if name],
            authors=_relationship_names(relationships, "author"),
            artists=_relationship_names(relationships, "artist"),
            cover_url=f"{_COVERS_BASE}/{provider_series_id}/{cover_file}.512.jpg" if cover_file else None,
            total_chapters=_as_int(attributes.get("lastChapter")),
            community_rating=self._rating(provider_series_id),
            external_ids={site: value for site, value in links.items() if site in _TRACKER_LINKS},
        )

    def _rating(self, provider_series_id: str) -> float | None:
        """Community rating via /statistics — best-effort (never blocks metadata)."""
        try:
            response = self._api.get(f"/statistics/manga/{provider_series_id}")
            stats = response.json().get("statistics", {}).get(provider_series_id, {})
            average = stats.get("rating", {}).get("average")
            return float(average) if average is not None else None
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return None

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
