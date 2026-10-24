"""Parallel AVIF encoding across a process pool — matches serial output."""

import io

import pytest
from PIL import Image
from src.core.config import settings
from src.media import encode_pool


def _png(shade: int) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 96), (shade, 60, 120)).save(buf, "PNG")
    return buf.getvalue()


def test_encode_pages_serial(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "encode_workers", 1)
    out = list(encode_pool.encode_pages([_png(i * 40) for i in range(3)]))
    assert len(out) == 3
    assert all(Image.open(io.BytesIO(data)).format == "AVIF" for data in out)


def test_encode_pages_parallel_matches_serial(monkeypatch: pytest.MonkeyPatch) -> None:
    raws = [_png(i * 40) for i in range(4)]

    monkeypatch.setattr(settings, "encode_workers", 1)
    serial = list(encode_pool.encode_pages(raws))

    monkeypatch.setattr(settings, "encode_workers", 2)
    encode_pool.shutdown()  # drop any pool so a fresh one picks up workers=2
    try:
        parallel = list(encode_pool.encode_pages(raws))
    finally:
        encode_pool.shutdown()

    # Encoding is deterministic → the parallel results are identical, and in page order.
    assert parallel == serial
    assert len(parallel) == 4


def test_thumbnails_have_an_independent_encoding_process_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.media.avif import ContentClass

    monkeypatch.setattr(settings, "encode_workers", 2)
    encode_pool.shutdown()
    try:
        pool = encode_pool._get_pool()
        pages = list(encode_pool.encode_pages([_png(30)]))
        cover = encode_pool.encode_thumbnail(_png(60), 32, ContentClass.COLOR_ART, None)
        assert encode_pool._get_pool() is pool
        assert encode_pool._get_pool("thumbnail") is not pool
        assert Image.open(io.BytesIO(pages[0])).format == "AVIF"
        image = Image.open(io.BytesIO(cover))
        assert image.format == "AVIF"
        assert max(image.size) == 32
        square = encode_pool.encode_thumbnail(_png(60), 32, ContentClass.COLOR_ART, 75, aspect=1.0)
        assert Image.open(io.BytesIO(square)).size == (32, 32)
    finally:
        encode_pool.shutdown()
