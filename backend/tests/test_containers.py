"""Tests for book-page containers."""

import zipfile
from pathlib import Path

import pytest
from src.core.exceptions import BadRequestError, NotFoundError
from src.media.containers import (
    ImageDirContainer,
    ZipContainer,
    is_cover_file,
    natural_key,
    open_container,
)


def test_natural_key_orders_numbers_numerically() -> None:
    names = ["10.jpg", "2.jpg", "1.jpg", "apple.png"]
    assert sorted(names, key=natural_key) == ["1.jpg", "2.jpg", "10.jpg", "apple.png"]


def test_image_dir_container_orders_and_reads(tmp_path: Path) -> None:
    for name, body in [("10.png", b"ten"), ("2.png", b"two"), ("1.png", b"one")]:
        _ = (tmp_path / name).write_bytes(body)
    _ = (tmp_path / "notes.txt").write_bytes(b"ignored")  # non-image is skipped

    container = ImageDirContainer(tmp_path)
    assert container.page_count() == 3
    assert [container.page_name(i) for i in range(3)] == ["1.png", "2.png", "10.png"]
    assert container.read_page(0) == b"one"
    assert container.read_page(2) == b"ten"


def test_image_dir_out_of_range_raises(tmp_path: Path) -> None:
    _ = (tmp_path / "1.png").write_bytes(b"x")
    container = ImageDirContainer(tmp_path)
    with pytest.raises(NotFoundError):
        _ = container.read_page(5)


def test_zip_container_reads_images_only(tmp_path: Path) -> None:
    archive = tmp_path / "ch1.cbz"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("002.jpg", b"second")
        zf.writestr("001.jpg", b"first")
        zf.writestr("info.txt", b"skip")
    with ZipContainer(archive) as container:
        assert container.page_count() == 2
        assert container.page_name(0) == "001.jpg"
        assert container.read_page(0) == b"first"
        assert container.read_page(1) == b"second"


def test_zip_container_rejects_corrupt(tmp_path: Path) -> None:
    bad = tmp_path / "broken.cbz"
    _ = bad.write_bytes(b"not a zip file at all")
    with pytest.raises(BadRequestError):
        _ = ZipContainer(bad)


def test_is_cover_file() -> None:
    assert is_cover_file("Cover.avif")
    assert is_cover_file("cover.jpg")
    assert is_cover_file("folder.png")
    assert not is_cover_file("001.jpg")  # a real page
    assert not is_cover_file("cover.txt")  # not an image


def test_cover_files_are_not_pages_in_image_dir(tmp_path: Path) -> None:
    for name, body in [("001.png", b"one"), ("002.png", b"two")]:
        _ = (tmp_path / name).write_bytes(body)
    _ = (tmp_path / "Cover.avif").write_bytes(b"cover")  # conventional cover — not a page
    _ = (tmp_path / "folder.jpg").write_bytes(b"folder")
    container = ImageDirContainer(tmp_path)
    assert container.page_count() == 2
    assert [container.page_name(i) for i in range(2)] == ["001.png", "002.png"]


def test_cover_files_are_not_pages_in_zip(tmp_path: Path) -> None:
    archive = tmp_path / "ch.cbz"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("Cover.avif", b"cover")
        zf.writestr("001.jpg", b"first")
        zf.writestr("002.jpg", b"second")
    with ZipContainer(archive) as container:
        assert container.page_count() == 2
        assert container.page_name(0) == "001.jpg"


def test_open_container_dispatch_and_errors(tmp_path: Path) -> None:
    _ = (tmp_path / "1.png").write_bytes(b"x")
    assert isinstance(open_container(tmp_path, "image_dir"), ImageDirContainer)

    with pytest.raises(BadRequestError):
        _ = open_container(tmp_path, "pdf")  # not supported yet
    with pytest.raises(NotFoundError):
        _ = open_container(tmp_path / "missing", "image_dir")
