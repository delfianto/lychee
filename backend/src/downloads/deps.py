"""Download dependencies (storage root — overridable in tests)."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import Depends

from src.core.config import settings


def get_storage_root() -> Path:
    return Path(settings.storage_path)


StorageRootDep = Annotated[Path, Depends(get_storage_root)]
