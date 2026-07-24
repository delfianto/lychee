"""Tests for the AVIF thumbnail store."""

import io
from pathlib import Path

from PIL import Image
from src.media.thumbnails import ThumbnailStore, ThumbVariant


def _source() -> Image.Image:
    return Image.new("RGB", (1000, 1500), (120, 60, 30))


def test_generate_all_writes_sharded_avif(tmp_path: Path) -> None:
    store = ThumbnailStore(tmp_path)
    store.generate_all("abcd1234", _source())

    cover = store.path_for("abcd1234", ThumbVariant.COVER)
    detail = store.path_for("abcd1234", ThumbVariant.DETAIL)
    assert cover.is_file() and detail.is_file()
    assert cover.parent.name == "ab"  # sharded by id[:2]

    img = Image.open(io.BytesIO(cover.read_bytes()))
    assert img.format == "AVIF"
    assert max(img.size) <= 320  # cover longest edge
    assert max(Image.open(io.BytesIO(detail.read_bytes())).size) <= 640


def test_generate_is_idempotent_until_overwrite(tmp_path: Path) -> None:
    store = ThumbnailStore(tmp_path)
    path = store.generate("id1", _source(), ThumbVariant.COVER)
    first_mtime = path.stat().st_mtime_ns

    # Second call without overwrite must be a no-op (same file, untouched).
    again = store.generate("id1", _source(), ThumbVariant.COVER)
    assert again == path
    assert path.stat().st_mtime_ns == first_mtime

    store.generate("id1", _source(), ThumbVariant.COVER, overwrite=True)
    assert path.is_file()


def test_read_missing_returns_none(tmp_path: Path) -> None:
    store = ThumbnailStore(tmp_path)
    assert store.read("nope", ThumbVariant.COVER) is None
    assert not store.exists("nope", ThumbVariant.COVER)
