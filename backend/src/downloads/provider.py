"""Download provider abstraction + registry (ADR 13).

A provider lists a remote series' chapters and fetches a chapter's page bytes.
The downloader (below) is provider-agnostic; MangaDex registers a concrete impl
at startup, and tests register a fake one — no network in the pipeline itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class RemoteChapter:
    provider_chapter_id: str
    number: str
    volume: int | None
    title: str | None
    language: str


class Provider(Protocol):
    id: str

    def list_chapters(self, provider_series_id: str, *, language: str = "en") -> list[RemoteChapter]:
        ...

    def fetch_pages(self, chapter: RemoteChapter) -> list[bytes]:
        ...


_REGISTRY: dict[str, Provider] = {}


def register_provider(provider: Provider) -> None:
    _REGISTRY[provider.id] = provider


def get_provider(provider_id: str) -> Provider | None:
    return _REGISTRY.get(provider_id)
