"""Reading-progress API schema."""

from __future__ import annotations

from pydantic import Field

from src.core.schema import CamelModel


class ProgressUpdate(CamelModel):
    page: int = Field(ge=0)
    # When omitted, completion is inferred from reaching the last page.
    completed: bool | None = None


class ChapterReadUpdate(CamelModel):
    chapter_ids: list[str] = Field(min_length=1, max_length=10000)
    completed: bool


class ChapterReadOut(CamelModel):
    updated: int
