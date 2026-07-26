"""Filesystem browse API schemas."""

from __future__ import annotations

from typing import Literal

from src.core.schema import CamelModel


class FsEntry(CamelModel):
    """One directory entry under the storage root."""

    name: str
    path: str  # absolute path on the server
    kind: Literal["dir", "file"]


class FsListing(CamelModel):
    """Directory listing for the path browser UI."""

    root: str  # absolute storage root (the browse ceiling)
    path: str  # absolute path currently listed
    parent: str | None  # absolute parent, or None when path == root
    entries: list[FsEntry]


class FsMkdir(CamelModel):
    """Create a directory under the storage root."""

    parent: str  # absolute (or relative-to-root) directory that will own the new folder
    name: str  # single path segment — no slashes
