"""AVIF thumbnail store — content-addressed and sharded.

Layout: ``<root>/<id[:2]>/<id>.<variant>.avif``. Two sizes keyed by the longest
edge — ``cover`` (~320px, grids) and ``detail`` (~640px, series/gallery hero).
Generation is idempotent and writes atomically (temp file + ``os.replace``), so a
half-written thumbnail can never be served.
"""

from __future__ import annotations

import os
import tempfile
from enum import StrEnum
from pathlib import Path

from PIL import Image

from src.media.artifacts import artifact_lock
from src.media.avif import ContentClass, load_image
from src.media.encode_pool import encode_thumbnail
from src.tasks.context import checkpoint


class ThumbVariant(StrEnum):
    """A thumbnail size."""

    COVER = "cover"
    DETAIL = "detail"


_MAX_EDGE: dict[ThumbVariant, int] = {
    ThumbVariant.COVER: 320,
    ThumbVariant.DETAIL: 640,
}


class ThumbnailStore:
    """Reads/writes AVIF thumbnails under a root directory."""

    def __init__(self, root: Path | str) -> None:
        self.root = Path(root)

    def path_for(self, thumb_id: str, variant: ThumbVariant) -> Path:
        return self.root / thumb_id[:2] / f"{thumb_id}.{variant.value}.avif"

    def exists(self, thumb_id: str, variant: ThumbVariant) -> bool:
        return self.path_for(thumb_id, variant).is_file()

    def read(self, thumb_id: str, variant: ThumbVariant) -> bytes | None:
        path = self.path_for(thumb_id, variant)
        return path.read_bytes() if path.is_file() else None

    def generate(
        self,
        thumb_id: str,
        source: Image.Image | bytes,
        variant: ThumbVariant,
        *,
        content_class: ContentClass = ContentClass.COLOR_ART,
        overwrite: bool = False,
        quality: int | None = None,
    ) -> Path:
        """Resize + AVIF-encode ``source`` into the store; idempotent unless ``overwrite``."""
        path = self.path_for(thumb_id, variant)
        with artifact_lock(str(path)):
            if path.is_file() and not overwrite:
                return path
            data = encode_thumbnail(source, _MAX_EDGE[variant], content_class, quality)
            checkpoint()
            _atomic_write(path, data)
            return path

    def generate_all(
        self,
        thumb_id: str,
        source: Image.Image | bytes,
        *,
        content_class: ContentClass = ContentClass.COLOR_ART,
        overwrite: bool = False,
        quality: int | None = None,
    ) -> None:
        """Generate every variant from one decode of the source."""
        image = load_image(source)
        for variant in ThumbVariant:
            self.generate(
                thumb_id,
                image,
                variant,
                content_class=content_class,
                overwrite=overwrite,
                quality=quality,
            )


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        dir=path.parent, prefix=f".{path.name}.", delete=False
    ) as handle:
        tmp = Path(handle.name)
        try:
            handle.write(data)
            handle.close()
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)
