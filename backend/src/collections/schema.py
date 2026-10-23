"""Collections (Lists) API schemas."""

from typing import Literal

from pydantic import Field

from src.catalog.schema import SeriesOut
from src.core.schema import CamelModel, UtcDatetime


class CollectionInfo(CamelModel):
    id: str
    name: str
    description: str | None = None
    provider: str | None = None
    provider_list_id: str | None = None
    source_url: str | None = None
    visibility: Literal["public", "private"] | None = None
    owned: bool = False
    followed: bool = False
    editable: bool = True
    last_synced_at: UtcDatetime | None = None


class CollectionOut(CollectionInfo):
    series_ids: list[str]
    kind: str | None = None


class CollectionDetailOut(CollectionInfo):
    series: list[SeriesOut]


class CollectionCreate(CamelModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = None
    provider: Literal["mangadex"] | None = None
    visibility: Literal["public", "private"] = "private"


class CollectionUpdate(CamelModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = None
    visibility: Literal["public", "private"] | None = None


class CollectionSeriesAdd(CamelModel):
    series_id: str


class ListImport(CamelModel):
    reference: str = Field(min_length=1, max_length=500)


class ListFollow(CamelModel):
    followed: bool


class RemoteListOut(CamelModel):
    id: str
    name: str
    visibility: str
    manga_count: int
    source_url: str


class ListChapterOut(CamelModel):
    chapter_id: str
    manga_id: str
    manga_title: str
    series_id: str | None = None
    number: str | None = None
    title: str | None = None
    language: str
    group: str | None = None
    uploaded_at: UtcDatetime | None = None
    source_url: str
