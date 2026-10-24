"""AVIF thumbnail store — content-addressed and sharded.

Layout: ``<root>/<id[:2]>/<id>.<variant>.avif``. One 640px-wide preview
per image: square gallery tiles or 2:3 portrait covers, without stretching.
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
from src.media.avif import ContentClass
from src.media.encode_pool import encode_thumbnail
from src.tasks.context import checkpoint


class ThumbVariant(StrEnum):
    """One fixed preview resolution, shaped for the UI frame."""

    COVER = "cover-v2"
    GALLERY = "gallery-v2"


PREVIEW_WIDTH = 640
PREVIEW_VERSION = 2
PREVIEW_QUALITY = 75


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
            # ImageOps.fit crops proportionally to the existing object-cover frame.
            aspect = 1.0 if variant is ThumbVariant.GALLERY else 2 / 3
            data = encode_thumbnail(
                source,
                PREVIEW_WIDTH,
                content_class,
                PREVIEW_QUALITY if quality is None else quality,
                aspect=aspect,
            )
            checkpoint()
            _atomic_write(path, data)
            # Remove only known legacy derivatives after the replacement is safe.
            for legacy in ("cover", "detail"):
                old = path.with_name(f"{thumb_id}.{legacy}.avif")
                old.unlink(missing_ok=True)
            return path


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
