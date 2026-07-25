"""FastAPI dependencies for the catalog (the thumbnail store)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends

from src.core.config import settings
from src.media.render_cache import RenderCache
from src.media.thumbnails import ThumbnailStore


def get_thumbnail_store() -> ThumbnailStore:
    """The on-disk AVIF thumbnail store (overridable in tests)."""
    return ThumbnailStore(Path(settings.storage_path) / "thumbnails")


ThumbnailStoreDep = Annotated[ThumbnailStore, Depends(get_thumbnail_store)]


def get_render_cache() -> RenderCache:
    """The on-disk AVIF page-render cache (overridable in tests)."""
    return RenderCache(Path(settings.storage_path) / "renders")


RenderCacheDep = Annotated[RenderCache, Depends(get_render_cache)]
