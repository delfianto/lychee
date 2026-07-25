"""Content-aware AVIF encoding.

lychee serves images as AVIF. The right chroma handling depends on the content —
line art, color art with text, and photographs each compress best differently:

- ``LINE_ART``  → grayscale (mono, 4:0:0), quality 63 — manga/manhwa; screentones
  stay crisp and files are tiny.
- ``COLOR_ART`` → 4:4:4, quality 80 — covers / official art: no chroma bleed
  around ink and lettering (4:2:0 softens those edges).
- ``PHOTO``     → 4:2:0, quality 60 — cosplay / photo galleries: subsampling is
  invisible on natural images and ~30–40% smaller.

CPU is a non-constraint (16-core), so we encode at a slow ``speed`` for best ratio.
``encode`` is a pure function of its input, so it is safe to fan out across a
``ProcessPoolExecutor`` (wired in the ingest/download task runner).
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from enum import StrEnum

from PIL import Image, ImageOps

# 0 = slowest / best ratio … 10 = fastest. CPU is free here, so favor ratio.
ENCODE_SPEED = 2

# Below this mean per-pixel RGB spread (0–255) an image is treated as grayscale.
_GRAY_SPREAD_THRESHOLD = 8.0
# Above this unique-color density (distinct / sampled pixels) a color image is a photo.
_PHOTO_COLOR_DENSITY = 0.5
_SAMPLE_EDGE = 64


class ContentClass(StrEnum):
    """How an image should be encoded."""

    LINE_ART = "line_art"
    COLOR_ART = "color_art"
    PHOTO = "photo"


@dataclass(frozen=True)
class AvifPreset:
    """AVIF encode parameters for a content class."""

    quality: int
    # None → encode from mode "L" (monochrome 4:0:0); otherwise a chroma subsampling.
    subsampling: str | None


_PRESETS: dict[ContentClass, AvifPreset] = {
    ContentClass.LINE_ART: AvifPreset(quality=63, subsampling=None),
    ContentClass.COLOR_ART: AvifPreset(quality=80, subsampling="4:4:4"),
    ContentClass.PHOTO: AvifPreset(quality=60, subsampling="4:2:0"),
}


def load_image(source: Image.Image | bytes) -> Image.Image:
    """Coerce raw bytes or a PIL image into a loaded, orientation-corrected image."""
    image = source if isinstance(source, Image.Image) else Image.open(io.BytesIO(source))
    image.load()
    return ImageOps.exif_transpose(image) or image


def classify(image: Image.Image) -> ContentClass:
    """Heuristically pick a content class from a cheap downsample.

    Near-zero per-pixel RGB spread ⇒ grayscale line art; otherwise a high density
    of distinct colors ⇒ photograph; else flat/sharp color art.
    """
    small = image.convert("RGB")
    small.thumbnail((_SAMPLE_EDGE, _SAMPLE_EDGE))
    raw = small.tobytes()  # interleaved R,G,B bytes
    count = (len(raw) // 3) or 1

    spread_total = 0
    colors: set[bytes] = set()
    for i in range(0, len(raw) - 2, 3):
        r, g, b = raw[i], raw[i + 1], raw[i + 2]
        spread_total += max(r, g, b) - min(r, g, b)
        colors.add(raw[i : i + 3])

    if spread_total / count < _GRAY_SPREAD_THRESHOLD:
        return ContentClass.LINE_ART
    if len(colors) / count > _PHOTO_COLOR_DENSITY:
        return ContentClass.PHOTO
    return ContentClass.COLOR_ART


def encode(
    image: Image.Image,
    *,
    content_class: ContentClass | None = None,
    quality: int | None = None,
) -> bytes:
    """Encode a PIL image to AVIF bytes using the (given or inferred) content preset.

    ``quality`` overrides the preset's quality (0–100, clamped) — e.g. for a
    user-configurable import quality — while subsampling stays per content class.
    """
    cls = content_class or classify(image)
    preset = _PRESETS[cls]
    q = preset.quality if quality is None else min(100, max(1, quality))
    buffer = io.BytesIO()
    if cls is ContentClass.LINE_ART:
        image.convert("L").save(buffer, format="AVIF", quality=q, speed=ENCODE_SPEED)
    else:
        image.convert("RGB").save(
            buffer,
            format="AVIF",
            quality=q,
            speed=ENCODE_SPEED,
            subsampling=preset.subsampling,
        )
    return buffer.getvalue()


def encode_bytes(
    source: bytes,
    *,
    content_class: ContentClass | None = None,
    quality: int | None = None,
) -> bytes:
    """Decode raw image bytes and re-encode as AVIF."""
    return encode(load_image(source), content_class=content_class, quality=quality)
