"""MangaDex provider — chapter listing, page download, metadata fetch, and search.

Runs over the rate-limited ``MangaDexClient`` (global 5 req/s + at-home 40/min,
429/retry handling, mandatory MangaDex@Home reporting). Implements both the
download ``Provider`` and the ``MetadataProvider`` contract from downloads/provider
(``search`` / ``get_metadata`` / ``list_new_chapters``), plus authed follows/status.
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from src.downloads.provider import CustomList, MangaMatch, RemoteChapter, SeriesMetadata
from src.providers.mangadex_client import MangaDexClient

_CONTENT_RATINGS = ["safe", "suggestive", "erotica", "pornographic"]

_PAGE_LIMIT = 100
_FEED_LIMIT = 500  # the feed endpoint allows up to 500 per page
_MAX_OFFSET = 10000  # MangaDex caps offset + limit at 10000
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


def _parse_manga(data: dict[str, Any], language: str, *, rating: float | None = None) -> SeriesMetadata:
    """Normalise a MangaDex manga object (with cover_art/author/artist expanded)."""
    manga_id = data["id"]
    attributes: dict[str, Any] = data.get("attributes", {})
    relationships: list[dict[str, Any]] = data.get("relationships", [])
    alt_titles = [
        (lang, value) for entry in attributes.get("altTitles", []) for lang, value in entry.items()
    ]
    tags = [
        (_localized(tag["attributes"].get("name"), language) or "", tag["attributes"].get("group", "genre"))
        for tag in attributes.get("tags", [])
        if tag.get("attributes")
    ]
    cover_file = _relationship_attr(relationships, "cover_art", "fileName")
    links: dict[str, str] = attributes.get("links") or {}
    return SeriesMetadata(
        provider_series_id=manga_id,
        title=_localized(attributes.get("title"), language) or manga_id,
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
        cover_url=f"{_COVERS_BASE}/{manga_id}/{cover_file}.512.jpg" if cover_file else None,
        total_chapters=_as_int(attributes.get("lastChapter")),
        community_rating=rating,
        external_ids={site: value for site, value in links.items() if site in _TRACKER_LINKS},
    )


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
                    "contentRating[]": _CONTENT_RATINGS,  # else erotica/pornographic are dropped
                    "includes[]": ["scanlation_group"],
                    "order[chapter]": "asc",
                    "limit": _FEED_LIMIT,
                    "offset": offset,
                },
            )
            body = response.json()
            for item in body.get("data", []):
                attributes: dict[str, Any] = item.get("attributes", {})
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
                        group_name=_relationship_attr(
                            item.get("relationships", []), "scanlation_group", "name"
                        ),
                        published_at=attributes.get("publishAt"),
                    )
                )
            offset += _FEED_LIMIT
            if offset >= min(int(body.get("total", 0)), _MAX_OFFSET):
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
        data = self._api.get(
            f"/manga/{provider_series_id}",
            params={"includes[]": ["cover_art", "author", "artist"]},
        ).json()["data"]
        return _parse_manga(data, language, rating=self._rating(provider_series_id))

    def list_tags(self, *, language: str = "en") -> list[tuple[str, str]]:
        """The canonical tag list — ``(name, group)`` for each tag from ``/manga/tag``."""
        data = self._api.get("/manga/tag").json()
        out: list[tuple[str, str]] = []
        for tag in data.get("data", []):
            name = _localized(tag["attributes"].get("name"), language) or ""
            if name:
                out.append((name, tag["attributes"].get("group", "genre")))
        return out

    def list_follows(self, *, language: str = "en") -> list[SeriesMetadata]:
        """The authed user's followed manga as normalised metadata (needs a Bearer token)."""
        results: list[SeriesMetadata] = []
        offset = 0
        while True:
            body = self._api.get(
                "/user/follows/manga",
                params={"includes[]": ["cover_art", "author", "artist"], "limit": 100, "offset": offset},
            ).json()
            results.extend(_parse_manga(data, language) for data in body.get("data", []))
            offset += 100
            if offset >= min(int(body.get("total", 0)), _MAX_OFFSET):
                break
        return results

    def reading_status(self) -> dict[str, str]:
        """Map of manga id → reading status for the authed user."""
        return self._api.get("/manga/status").json().get("statuses", {}) or {}

    def list_custom_lists(self) -> list[CustomList]:
        """The authed user's MDLists + their member manga ids (needs a Bearer token). The
        manga ids ride in each list's relationships, so no per-list fetch is needed."""
        results: list[CustomList] = []
        offset = 0
        while True:
            body = self._api.get("/user/list", params={"limit": 100, "offset": offset}).json()
            for data in body.get("data", []):
                name = data.get("attributes", {}).get("name") or data["id"]  # MDList name is plain
                manga_ids = [
                    rel["id"] for rel in data.get("relationships", []) if rel.get("type") == "manga"
                ]
                results.append(
                    CustomList(provider_list_id=data["id"], name=name, manga_ids=manga_ids)
                )
            offset += 100
            if offset >= min(int(body.get("total", 0)), _MAX_OFFSET):
                break
        return results

    def read_markers(self, manga_ids: list[str]) -> dict[str, list[str]]:
        """Map of manga id → read chapter ids for the authed user (batched, grouped)."""
        result: dict[str, list[str]] = {}
        for start in range(0, len(manga_ids), 100):  # /manga/read caps the id list
            chunk = manga_ids[start : start + 100]
            body = self._api.get("/manga/read", params={"ids[]": chunk, "grouped": "true"}).json()
            data = body.get("data", {})
            if isinstance(data, dict):
                for manga_id, chapter_ids in data.items():
                    result[manga_id] = list(chapter_ids or [])
        return result

    def _rating(self, provider_series_id: str) -> float | None:
        """Community rating via /statistics — best-effort (never blocks metadata)."""
        try:
            response = self._api.get(f"/statistics/manga/{provider_series_id}")
            stats = response.json().get("statistics", {}).get(provider_series_id, {})
            average = stats.get("rating", {}).get("average")
            return float(average) if average is not None else None
        except (httpx.HTTPError, KeyError, TypeError, ValueError):
            return None

    def _at_home(self, chapter_id: str) -> dict[str, Any]:
        return self._api.get(f"/at-home/server/{chapter_id}", athome=True).json()

    def fetch_pages(self, chapter: RemoteChapter, *, data_saver: bool = False) -> list[bytes]:
        server = self._at_home(chapter.provider_chapter_id)
        quality = "data-saver" if data_saver else "data"
        chapter_hash = server["chapter"]["hash"]
        files: list[str] = server["chapter"]["dataSaver" if data_saver else "data"]
        base = server["baseUrl"]  # mutated if a node expires (403) mid-chapter
        pages: list[bytes] = []
        for filename in files:
            content, base = self._fetch_page(
                chapter.provider_chapter_id, base, quality, chapter_hash, filename
            )
            pages.append(content)
        return pages

    def _fetch_page(
        self, chapter_id: str, base_url: str, quality: str, chapter_hash: str, filename: str
    ) -> tuple[bytes, str]:
        """Download one page; on 403 (expired baseUrl) re-assign a node and retry once.

        Returns (bytes, base_url) so the caller reuses a refreshed node for later pages.
        """
        url = f"{base_url}/{quality}/{chapter_hash}/{filename}"
        started = time.monotonic()
        try:
            page = self._api.get_bytes(url)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 403:
                self._report(url, success=False, nbytes=0, started=started, cached=False)
                raise
            base_url = self._at_home(chapter_id)["baseUrl"]  # node expired → re-assign
            url = f"{base_url}/{quality}/{chapter_hash}/{filename}"
            try:
                page = self._api.get_bytes(url)
            except httpx.HTTPError:
                self._report(url, success=False, nbytes=0, started=started, cached=False)
                raise
        except httpx.HTTPError:
            self._report(url, success=False, nbytes=0, started=started, cached=False)
            raise
        content = page.content
        cached = page.headers.get("X-Cache", "").upper().startswith("HIT")
        self._report(url, success=True, nbytes=len(content), started=started, cached=cached)
        return content, base_url

    def _report(self, url: str, *, success: bool, nbytes: int, started: float, cached: bool) -> None:
        self._api.report(
            url,
            success=success,
            nbytes=nbytes,
            duration_ms=int((time.monotonic() - started) * 1000),
            cached=cached,
        )
