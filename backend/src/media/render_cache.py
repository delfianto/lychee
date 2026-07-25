"""On-demand page render cache — width-capped AVIF renders of book pages.

Serving a page with ``?w=<width>`` returns the page re-encoded as AVIF downscaled to
at most that width (never upscaled), cached on disk so repeat requests are free.
Keyed by book id + page index + width, sharded like the thumbnail store.
"""

from __future__ import annotations

import os
from pathlib import Path

from PIL import Image

from src.media.avif import encode, load_image

MIN_WIDTH = 100
MAX_WIDTH = 3000


def clamp_width(width: int) -> int:
    return max(MIN_WIDTH, min(MAX_WIDTH, width))


def render_width(source: bytes, width: int) -> bytes:
    """Re-encode ``source`` as AVIF, downscaled to at most ``width`` px wide (no upscale)."""
    image = load_image(source)
    if image.width > width:
        height = round(image.height * width / image.width)
        image = image.resize((width, height), Image.Resampling.LANCZOS)
    return encode(image)


class RenderCache:
    """Disk cache of width-capped AVIF page renders."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def _path(self, book_id: str, index: int, width: int) -> Path:
        return self.root / book_id[:2] / f"{book_id}-{index}-{width}.avif"

    def get(self, book_id: str, index: int, width: int) -> bytes | None:
        path = self._path(book_id, index, width)
        return path.read_bytes() if path.is_file() else None

    def put(self, book_id: str, index: int, width: int, data: bytes) -> None:
        path = self._path(book_id, index, width)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(f"{path.name}.tmp")
        _ = tmp.write_bytes(data)
        os.replace(tmp, path)  # atomic
