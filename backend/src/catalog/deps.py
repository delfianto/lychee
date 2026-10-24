"""FastAPI dependencies for the catalog (the thumbnail store)."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Annotated

from anyio import CapacityLimiter
from fastapi import Depends, Request

from src.core.config import settings
from src.core.persistence.database import DbSession
from src.media.render_cache import RenderCache
from src.media.storage import thumbnail_root
from src.media.thumbnails import ThumbnailStore


def get_thumbnail_store(db: DbSession) -> ThumbnailStore:
    """The on-disk AVIF thumbnail store (overridable in tests)."""
    return ThumbnailStore(thumbnail_root(db))


ThumbnailStoreDep = Annotated[ThumbnailStore, Depends(get_thumbnail_store)]


def get_render_cache() -> RenderCache:
    """The on-disk AVIF page-render cache (overridable in tests)."""
    return RenderCache(Path(settings.storage_path) / "renders")


RenderCacheDep = Annotated[RenderCache, Depends(get_render_cache)]


async def get_image_limiter(request: Request) -> AsyncGenerator[CapacityLimiter]:
    """Admit images before DB dependencies, then use a separate thread budget.

    Waiting image requests must not hold database connections or ordinary API
    workers. Admission and worker tokens are separate because run_sync acquires
    its own token on the same requesting task.
    """
    async with request.app.state.image_admission:
        yield request.app.state.image_limiter


ImageLimiterDep = Annotated[CapacityLimiter, Depends(get_image_limiter)]
