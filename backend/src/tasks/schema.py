"""Task API schema."""

from __future__ import annotations

from typing import Any

from src.core.schema import CamelModel


class TaskOut(CamelModel):
    id: str
    kind: str
    label: str
    status: str
    progress: int
    detail: str | None = None
    result: dict[str, Any] | None = None
