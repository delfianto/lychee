"""Book-page containers — read a book's pages without unpacking it.

A ``BookContainer`` exposes an ordered, 0-indexed page list and reads one page's
raw bytes on demand. It handles the zero-system-dependency kinds: a directory of
images, a CBZ/ZIP archive, and a downloaded AVIF directory. (RAR/7z/PDF/EPUB are
not planned — CBZ + image directories cover the common cases.)

Pages are ordered by a natural sort of their names so ``2.jpg`` precedes ``10.jpg``.
"""

from __future__ import annotations

import re
import zipfile
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable
from functools import lru_cache
from pathlib import Path
from typing import Self

from src.core.exceptions import BadRequestError, NotFoundError

IMAGE_EXTS = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff", ".avif"}
)

_NUM = re.compile(r"(\d+)")


def natural_key(name: str) -> list[str | int]:
    """Sort key so embedded numbers order numerically (``2`` before ``10``)."""
    return [int(part) if part.isdigit() else part.lower() for part in _NUM.split(name)]


def _is_image(name: str) -> bool:
    return Path(name).suffix.lower() in IMAGE_EXTS


_COVER_STEMS = frozenset({"cover", "folder"})


def is_cover_file(name: str) -> bool:
    """A conventional cover image (``Cover.avif`` / ``cover.jpg`` / ``folder.png``) — a
    series/book cover, never a readable page. Excluded from page lists + scan detection."""
    path = Path(name)
    return path.suffix.lower() in IMAGE_EXTS and path.stem.lower() in _COVER_STEMS


class BookContainer(ABC):
    """An ordered, 0-indexed collection of page images."""

    @abstractmethod
    def page_count(self) -> int: ...

    @abstractmethod
    def page_name(self, index: int) -> str: ...

    @abstractmethod
    def read_page(self, index: int) -> bytes: ...

    def close(self) -> None:  # noqa: B027 — optional override; default is a no-op
        """Release any held resources (default: nothing)."""

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def _check(self, index: int) -> None:
        if not 0 <= index < self.page_count():
            raise NotFoundError(f"page {index} out of range (0–{self.page_count() - 1})")


@lru_cache(maxsize=512)
def _dir_page_names(path_str: str, _mtime: float) -> tuple[str, ...]:
    """Sorted image names in a directory, cached per (path, mtime) — so the repeated page
    requests for one book skip re-scanning + re-sorting the directory each time."""
    directory = Path(path_str)
    return tuple(
        sorted(
            (
                p.name
                for p in directory.iterdir()
                if p.is_file() and _is_image(p.name) and not is_cover_file(p.name)
            ),
            key=natural_key,
        )
    )


class ImageDirContainer(BookContainer):
    """A directory whose direct children are page images (also serves AVIF dirs)."""

    def __init__(self, path: Path) -> None:
        self._dir = path
        self._names = _dir_page_names(str(path), path.stat().st_mtime)

    def page_count(self) -> int:
        return len(self._names)

    def page_name(self, index: int) -> str:
        self._check(index)
        return self._names[index]

    def read_page(self, index: int) -> bytes:
        self._check(index)
        return (self._dir / self._names[index]).read_bytes()


class ZipContainer(BookContainer):
    """A CBZ/ZIP archive of page images."""

    def __init__(self, path: Path) -> None:
        try:
            self._zip = zipfile.ZipFile(path)
        except zipfile.BadZipFile as exc:
            raise BadRequestError(f"corrupt archive: {path.name}") from exc
        self._names = sorted(
            (n for n in self._zip.namelist() if _is_image(n) and not is_cover_file(n)),
            key=natural_key,
        )

    def page_count(self) -> int:
        return len(self._names)

    def page_name(self, index: int) -> str:
        self._check(index)
        return self._names[index]

    def read_page(self, index: int) -> bytes:
        self._check(index)
        return self._zip.read(self._names[index])

    def close(self) -> None:
        self._zip.close()


# content_kind (Book.content_kind) → container factory.
_DIR_KINDS = frozenset({"image_dir", "avif_dir"})
_ZIP_KINDS = frozenset({"cbz", "zip"})


def open_container(path: Path, content_kind: str) -> BookContainer:
    """Open the container for ``path`` given its ``Book.content_kind``."""
    if not path.exists():
        raise NotFoundError(f"book path does not exist: {path}")
    if content_kind in _DIR_KINDS:
        return ImageDirContainer(path)
    if content_kind in _ZIP_KINDS:
        return ZipContainer(path)
    raise BadRequestError(f"unsupported container kind: {content_kind!r}")


def write_cbz(
    dest: Path,
    pages: Iterable[bytes],
    *,
    on_page: Callable[[int], None] | None = None,
) -> tuple[int, int]:
    """Pack ``pages`` into a CBZ at ``dest`` as ``001.avif``, ``002.avif``, … using
    ``ZIP_STORED`` — the pages are already compressed (AVIF), so DEFLATE would only
    burn CPU for ~no size gain. Writes to a temp file then atomically renames, so a
    crash never leaves a half-written archive. ``on_page`` fires after each page (for
    progress). Returns ``(page_count, total_bytes)``.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".tmp")
    count = 0
    size = 0
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_STORED) as archive:
            for data in pages:
                count += 1
                archive.writestr(f"{count:03d}.avif", data)
                size += len(data)
                if on_page is not None:
                    on_page(count)
        tmp.replace(dest)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return count, size
