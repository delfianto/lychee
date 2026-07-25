"""Tests for content-aware AVIF encoding."""

import io
import os

from PIL import Image
from src.media.avif import ContentClass, classify, encode, encode_bytes


def _line_art() -> Image.Image:
    """White page with black vertical lines — grayscale content in RGB mode."""
    img = Image.new("RGB", (128, 160), "white")
    for x in range(0, 128, 8):
        for y in range(160):
            img.putpixel((x, y), (0, 0, 0))
    return img


def _flat_color() -> Image.Image:
    """Four solid color quadrants — few unique colors, clearly colored."""
    img = Image.new("RGB", (128, 128))
    colors = [(200, 30, 30), (30, 200, 30), (30, 30, 200), (200, 200, 30)]
    for i, (cx, cy) in enumerate([(0, 0), (64, 0), (0, 64), (64, 64)]):
        for x in range(cx, cx + 64):
            for y in range(cy, cy + 64):
                img.putpixel((x, y), colors[i])
    return img


def _photo() -> Image.Image:
    """Random RGB noise — many unique colors, high spread."""
    return Image.frombytes("RGB", (128, 128), os.urandom(128 * 128 * 3))


def test_classify_line_art() -> None:
    assert classify(_line_art()) is ContentClass.LINE_ART


def test_classify_flat_color() -> None:
    assert classify(_flat_color()) is ContentClass.COLOR_ART


def test_classify_photo() -> None:
    assert classify(_photo()) is ContentClass.PHOTO


def test_encode_produces_valid_avif() -> None:
    data = encode(_flat_color())
    assert data[4:8] == b"ftyp"  # ISO-BMFF box; AVIF brand follows
    assert b"avif" in data[:32]
    decoded = Image.open(io.BytesIO(data))
    decoded.load()
    assert decoded.format == "AVIF"
    assert decoded.size == (128, 128)


def test_encode_line_art_is_monochrome_and_smaller() -> None:
    art = _line_art()
    mono = encode(art, content_class=ContentClass.LINE_ART)
    color = encode(art, content_class=ContentClass.COLOR_ART)
    # Both decode fine; the mono path should not be larger than full 4:4:4 color.
    assert Image.open(io.BytesIO(mono)).format == "AVIF"
    assert len(mono) <= len(color)


def test_encode_bytes_roundtrip() -> None:
    src = io.BytesIO()
    _flat_color().save(src, format="PNG")
    data = encode_bytes(src.getvalue(), content_class=ContentClass.COLOR_ART)
    assert Image.open(io.BytesIO(data)).format == "AVIF"


def test_quality_override_shrinks_output() -> None:
    photo = _photo()  # noisy content shows a clear size delta across quality
    low = encode(photo, content_class=ContentClass.PHOTO, quality=20)
    high = encode(photo, content_class=ContentClass.PHOTO, quality=90)
    assert len(low) < len(high)
    assert Image.open(io.BytesIO(low)).format == "AVIF"


def test_quality_none_matches_preset() -> None:
    art = _flat_color()
    # quality=None must reproduce the preset path byte-for-byte (deterministic encode).
    assert encode(art, content_class=ContentClass.COLOR_ART, quality=None) == encode(
        art, content_class=ContentClass.COLOR_ART
    )
