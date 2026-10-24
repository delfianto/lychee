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


class ImageProcessingUpdate(CamelModel):
    conversion_workers: int = Field(ge=1, le=64, strict=True)
    thumbnail_workers: int = Field(ge=1, le=64, strict=True)


class ImageProcessingOut(ImageProcessingUpdate):
    cpu_threads: int
    recommended_conversion_workers: int
    recommended_thumbnail_workers: int
