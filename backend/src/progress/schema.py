"""Reading-progress API schema."""

from __future__ import annotations

from src.core.schema import CamelModel


class ProgressUpdate(CamelModel):
    page: int
    # When omitted, completion is inferred from reaching the last page.
    completed: bool | None = None
