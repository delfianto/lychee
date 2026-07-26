"""Filesystem browse API — storage-root-scoped directory listings for the path picker."""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from src.downloads.deps import StorageRootDep
from src.fs import service
from src.fs.schema import FsEntry, FsListing, FsMkdir

router = APIRouter(prefix="/api/fs", tags=["fs"])


@router.get("")
def browse(
    storage: StorageRootDep,
    path: str | None = Query(
        default=None,
        description="Absolute path under the storage root, or relative to it. Empty = root.",
    ),
) -> FsListing:
    """List a directory under the configured storage root.

    Used by the Add Library / Import path browsers so operators pick a folder
    instead of typing a server path. Paths outside the storage root are rejected.
    """
    return service.list_directory(storage, path)


@router.post("/mkdir", status_code=status.HTTP_201_CREATED)
def mkdir(storage: StorageRootDep, data: FsMkdir) -> FsEntry:
    """Create a new folder under the storage root (path browser “New folder”)."""
    return service.create_directory(storage, data.parent, data.name)
