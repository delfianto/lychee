"""Task API schema."""

from __future__ import annotations

from typing import Any

from pydantic import Field

from src.core.schema import CamelModel
from src.media.schema import ImageProcessingUpdate


class TaskOut(CamelModel):
    id: str
    kind: str
    label: str
    status: str
    progress: int
    detail: str | None = None
    result: dict[str, Any] | None = None
    phases: dict[str, dict[str, int]] = Field(default_factory=dict)


class WorkerSettingsUpdate(ImageProcessingUpdate):
    download_workers: int = Field(ge=1, le=10, strict=True)
    scan_metadata_workers: int = Field(ge=1, le=10, strict=True)


class WorkerSettingsOut(WorkerSettingsUpdate):
    cpu_threads: int
    recommended_conversion_workers: int
    recommended_thumbnail_workers: int
