"""Tests for the AVIF thumbnail store."""

import io
from pathlib import Path

import pytest
from PIL import Image
from src.media.thumbnails import ThumbnailStore, ThumbVariant


def _source() -> Image.Image:
    return Image.new("RGB", (1000, 1500), (120, 60, 30))


def test_generate_writes_one_sharded_cover_preview(tmp_path: Path) -> None:
    store = ThumbnailStore(tmp_path)
    store.generate("abcd1234", _source(), ThumbVariant.COVER)

    cover = store.path_for("abcd1234", ThumbVariant.COVER)
    assert cover.is_file()
    assert len(list(tmp_path.rglob("*.avif"))) == 1
    assert cover.parent.name == "ab"  # sharded by id[:2]

    img = Image.open(io.BytesIO(cover.read_bytes()))
    assert img.format == "AVIF"
    assert img.size == (640, 960)  # portrait UI frame, not a stretched square


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


@pytest.mark.parametrize("source_size", [(1200, 1800), (1800, 1200), (1200, 1200)])
@pytest.mark.parametrize(
    "variant,expected", [(ThumbVariant.GALLERY, (640, 640)), (ThumbVariant.COVER, (640, 960))]
)
def test_preview_matches_ui_frame_without_distorting_portrait_or_landscape_sources(
    tmp_path: Path, source_size: tuple[int, int], variant: ThumbVariant, expected: tuple[int, int]
) -> None:
    from PIL import ImageDraw

    source = Image.new("RGB", source_size, "black")
    x, y = source.width // 2, source.height // 2
    ImageDraw.Draw(source).ellipse((x - 150, y - 150, x + 150, y + 150), fill="white")
    store = ThumbnailStore(tmp_path)
    path = store.generate("shape", source, variant)
    decoded = Image.open(path)
    assert decoded.size == expected
    bounds = (
        decoded.convert("L").point([255 if value > 200 else 0 for value in range(256)]).getbbox()
    )
    assert bounds is not None
    assert abs((bounds[2] - bounds[0]) - (bounds[3] - bounds[1])) <= 2
    assert len(list(tmp_path.rglob("*.avif"))) == 1


def test_small_source_is_not_upscaled(tmp_path: Path) -> None:
    store = ThumbnailStore(tmp_path)
    path = store.generate("small", Image.new("RGB", (80, 120)), ThumbVariant.GALLERY)
    assert Image.open(path).size == (80, 80)


def test_replacement_removes_legacy_derivatives_after_success_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.media import thumbnails

    store = ThumbnailStore(tmp_path)
    shard = tmp_path / "ab"
    shard.mkdir()
    legacy = [shard / "abcd.cover.avif", shard / "abcd.detail.avif"]
    for path in legacy:
        path.write_bytes(b"legacy")
    original_encode = thumbnails.encode_thumbnail

    def fail(*_args, **_kwargs):
        raise ValueError("failed encoder")

    monkeypatch.setattr(thumbnails, "encode_thumbnail", fail)
    with pytest.raises(ValueError, match="failed encoder"):
        store.generate("abcd", _source(), ThumbVariant.GALLERY)
    assert all(path.exists() for path in legacy)
    monkeypatch.setattr(thumbnails, "encode_thumbnail", original_encode)
    replacement = store.generate("abcd", _source(), ThumbVariant.GALLERY)
    assert Image.open(replacement).size == (640, 640)
    assert not any(path.exists() for path in legacy)
