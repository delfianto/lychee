"""End-to-end library scan tests (create library → scan → reconcile)."""

import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image


def _png_bytes(shade: int = 80) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (20, 30), (shade, 80, 120)).save(buf, "PNG")
    return buf.getvalue()


def _cbz(path: Path, pages: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for i in range(pages):
            archive.writestr(f"{i + 1:03d}.png", _png_bytes(i * 20))


def _image_dir(path: Path, pages: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for i in range(pages):
        _ = (path / f"{i + 1:03d}.png").write_bytes(_png_bytes(i * 15))


def _make_library(tmp_path: Path) -> Path:
    root = tmp_path / "lib"
    _cbz(root / "Berserk" / "Vol. 01" / "Chapter 1.cbz", 3)
    _cbz(root / "Berserk" / "Vol. 01" / "Chapter 2.cbz", 2)
    _image_dir(root / "Solo Leveling", 3)
    return root


def _create_and_scan(client: TestClient, root: Path) -> tuple[str, dict[str, int]]:
    created = client.post(
        "/api/libraries", json={"name": "Test", "path": str(root), "kind": "manga"}
    )
    assert created.status_code == 201
    library_id = created.json()["id"]
    result = client.post(f"/api/libraries/{library_id}/scan")
    assert result.status_code == 200
    return library_id, result.json()


def test_scan_creates_series_books_chapters(client: TestClient, tmp_path: Path) -> None:
    root = _make_library(tmp_path)
    _, summary = _create_and_scan(client, root)
    assert summary["seriesAdded"] == 2
    assert summary["booksAdded"] == 3

    series = {s["title"]: s for s in client.get("/api/series").json()["items"]}
    assert set(series) == {"Berserk", "Solo Leveling"}
    assert series["Berserk"]["chapterCount"] == 2
    assert series["Solo Leveling"]["chapterCount"] == 1

    chapters = client.get(f"/api/series/{series['Berserk']['id']}/chapters").json()
    assert len(chapters) == 1  # one volume group
    assert chapters[0]["volume"] == 1
    assert [c["number"] for c in chapters[0]["chapters"]] == ["2", "1"]


def test_scan_is_idempotent(client: TestClient, tmp_path: Path) -> None:
    root = _make_library(tmp_path)
    library_id, _ = _create_and_scan(client, root)

    again = client.post(f"/api/libraries/{library_id}/scan").json()
    assert again == {"seriesAdded": 0, "booksAdded": 0, "booksUpdated": 0, "booksRemoved": 0}


def test_scan_soft_deletes_missing(client: TestClient, tmp_path: Path) -> None:
    root = _make_library(tmp_path)
    library_id, _ = _create_and_scan(client, root)

    (root / "Berserk" / "Vol. 01" / "Chapter 2.cbz").unlink()
    result = client.post(f"/api/libraries/{library_id}/scan").json()
    assert result["booksRemoved"] == 1

    series = {s["title"]: s for s in client.get("/api/series").json()["items"]}
    assert series["Berserk"]["chapterCount"] == 1


def test_library_list_reports_series_count(client: TestClient, tmp_path: Path) -> None:
    root = _make_library(tmp_path)
    library_id, _ = _create_and_scan(client, root)

    libraries = {lib["id"]: lib for lib in client.get("/api/libraries").json()}
    assert libraries[library_id]["seriesCount"] == 2
    assert libraries[library_id]["lastScan"] is not None
