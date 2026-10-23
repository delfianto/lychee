"""Thumbnail storage settings API."""

from pydantic import Field

from src.core.schema import CamelModel


class ThumbnailStorageUpdate(CamelModel):
    # null resets to STORAGE_PATH/thumbnails.
    path: str | None = Field(max_length=4096)


class ThumbnailStorageOut(CamelModel):
    path: str | None
    default_path: str
    effective_path: str
