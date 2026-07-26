"""Download provider abstraction + registry.

A provider lists a remote series' chapters and fetches a chapter's page bytes.
The downloader (below) is provider-agnostic; MangaDex registers a concrete impl
at startup, and tests register a fake one — no network in the pipeline itself.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, cast

# Called as on_page(done, total) while pages are fetched from the provider.
PageProgress = Callable[[int, int], None]


@dataclass(frozen=True)
class RemoteChapter:
    provider_chapter_id: str
    number: str
    volume: int | None
    title: str | None
    language: str
    group_name: str | None = None
    published_at: str | None = None  # ISO 8601 from the provider (→ source_uploaded_at)


class Provider(Protocol):
    id: str

    def list_chapters(
        self, provider_series_id: str, *, language: str = "en"
    ) -> list[RemoteChapter]: ...

    def fetch_pages(
        self,
        chapter: RemoteChapter,
        *,
        data_saver: bool = False,
        on_page: PageProgress | None = None,
    ) -> list[bytes]: ...


# --- Metadata side of the abstraction ------------------------------------------
# Declared here so the matching / refresh / sync services depend on the contract;
# MangaDexProvider implements it.


@dataclass(frozen=True)
class MangaMatch:
    """A search hit when matching a local series to a provider entry."""

    provider_series_id: str
    title: str
    year: int | None = None
    status: str | None = None
    cover_url: str | None = None


@dataclass
class SeriesMetadata:
    """Normalised provider metadata for one series, before mapping to the model."""

    provider_series_id: str
    title: str
    alt_titles: list[tuple[str, str]] = field(default_factory=list)  # (language, title)
    description: str | None = None
    status: str | None = None
    year: int | None = None
    content_rating: str | None = None
    demographic: str | None = None
    original_language: str | None = None
    tags: list[tuple[str, str]] = field(default_factory=list)  # (name, group)
    authors: list[str] = field(default_factory=list)
    artists: list[str] = field(default_factory=list)
    cover_url: str | None = None
    total_chapters: int | None = None
    community_rating: float | None = None
    external_ids: dict[str, str] = field(default_factory=dict)  # site -> id: al, mal, mu, …


@dataclass(frozen=True)
class CustomList:
    """A provider custom list (e.g. a MangaDex MDList) + its member manga ids."""

    provider_list_id: str
    name: str
    manga_ids: list[str] = field(default_factory=list)


class MetadataProvider(Protocol):
    """Search + metadata + new-chapter discovery (implemented by MangaDexProvider)."""

    id: str

    def search(self, title: str, *, limit: int = 5) -> list[MangaMatch]: ...

    def get_metadata(self, provider_series_id: str, *, language: str = "en") -> SeriesMetadata: ...

    def list_new_chapters(
        self, provider_series_id: str, *, known: set[str], language: str = "en"
    ) -> list[RemoteChapter]: ...

    def list_tags(self, *, language: str = "en") -> list[tuple[str, str]]:
        """The provider's canonical tag list as ``(name, group)`` pairs."""
        ...


_REGISTRY: dict[str, Provider] = {}


def register_provider(provider: Provider) -> None:
    _REGISTRY[provider.id] = provider


def get_provider(provider_id: str) -> Provider | None:
    return _REGISTRY.get(provider_id)


def get_metadata_provider(provider_id: str) -> MetadataProvider | None:
    """The registered provider viewed as a MetadataProvider, if it supports metadata."""
    provider = _REGISTRY.get(provider_id)
    if provider is not None and hasattr(provider, "get_metadata"):
        return cast(MetadataProvider, provider)
    return None
