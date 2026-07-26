"""List / create directories under the configured storage root (path-traversal safe)."""

from __future__ import annotations

from pathlib import Path

from src.core.exceptions import BadRequestError, ConflictError, NotFoundError
from src.fs.schema import FsEntry, FsListing


def _resolved_root(storage_root: Path) -> Path:
    return storage_root.expanduser().resolve()


def resolve_under_root(storage_root: Path, path: str | None) -> Path:
    """Resolve ``path`` to an absolute path that must stay under ``storage_root``.

    ``path`` may be empty (→ root), relative to the root, or absolute (only accepted
    if it still resolves under the root). Symlink escapes are rejected via resolve().
    """
    root = _resolved_root(storage_root)
    if not path or path in {".", "/"}:
        return root

    candidate = Path(path).expanduser()
    target = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()

    if not target.is_relative_to(root):
        raise BadRequestError("path escapes storage root")
    return target


def list_directory(storage_root: Path, path: str | None = None) -> FsListing:
    """Return a directory listing for the path browser.

    Directories first, then files; case-insensitive name order. Dotfiles are
    omitted (noise for library/import picking). Only the storage root and its
    descendants are visible — never the rest of the host filesystem.
    """
    root = _resolved_root(storage_root)
    target = resolve_under_root(root, path)

    if not target.exists():
        raise NotFoundError(f"path {target!s} not found")
    if not target.is_dir():
        raise BadRequestError("not a directory")

    entries: list[FsEntry] = []
    try:
        children = list(target.iterdir())
    except OSError as exc:
        raise BadRequestError(f"cannot read directory: {exc}") from exc

    children.sort(key=lambda p: (not p.is_dir(), p.name.casefold()))
    for child in children:
        if child.name.startswith("."):
            continue
        try:
            is_dir = child.is_dir()
        except OSError:
            continue
        entries.append(FsEntry(name=child.name, path=str(child), kind="dir" if is_dir else "file"))

    parent: str | None = None if target == root else str(target.parent)
    return FsListing(root=str(root), path=str(target), parent=parent, entries=entries)


def _validate_folder_name(name: str) -> str:
    """Single path segment: non-empty, no separators, no ``.`` / ``..``."""
    cleaned = name.strip()
    if not cleaned or cleaned in {".", ".."}:
        raise BadRequestError("invalid folder name")
    if "/" in cleaned or "\\" in cleaned or "\0" in cleaned:
        raise BadRequestError("folder name must be a single path segment")
    if cleaned.startswith("."):
        raise BadRequestError("folder name cannot start with a dot")
    return cleaned


def create_directory(storage_root: Path, parent: str, name: str) -> FsEntry:
    """Create ``parent/name`` under the storage root. Returns the new entry."""
    root = _resolved_root(storage_root)
    folder_name = _validate_folder_name(name)
    parent_path = resolve_under_root(root, parent)

    if not parent_path.exists():
        raise NotFoundError(f"path {parent_path!s} not found")
    if not parent_path.is_dir():
        raise BadRequestError("parent is not a directory")

    # Join then resolve; reject anything that still escapes (e.g. weird unicode).
    target = (parent_path / folder_name).resolve()
    if not target.is_relative_to(root):
        raise BadRequestError("path escapes storage root")
    if target.exists():
        raise ConflictError(f"already exists: {folder_name!r}")

    try:
        target.mkdir(parents=False)
    except OSError as exc:
        raise BadRequestError(f"cannot create folder: {exc}") from exc

    return FsEntry(name=folder_name, path=str(target), kind="dir")
