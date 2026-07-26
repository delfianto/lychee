"""Collections (Lists) API schemas."""

from __future__ import annotations

from src.catalog.schema import SeriesOut
from src.core.schema import CamelModel


class CollectionOut(CamelModel):
    id: str
    name: str
    description: str | None = None
    series_ids: list[str]
    # "manga" | "comic" | "gallery" if every member series shares one kind, "mixed" if
    # they differ, null if the list is empty — lets the UI group/tab lists by content type.
    kind: str | None = None


class CollectionDetailOut(CamelModel):
    id: str
    name: str
    description: str | None = None
    series: list[SeriesOut]


class CollectionCreate(CamelModel):
    name: str
    description: str | None = None


class CollectionUpdate(CamelModel):
    name: str | None = None
    description: str | None = None


class CollectionSeriesAdd(CamelModel):
    series_id: str
