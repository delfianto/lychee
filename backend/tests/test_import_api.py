"""End-to-end local import tests (enable → import file/folder → transcoded AVIF)."""

import io
import zipfile
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from src.media.thumbnails import ThumbnailStore, ThumbVariant
from src.tasks.queue import queue


def _png(shade: int = 90) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (24, 32), (shade, 90, 140)).save(buf, "PNG")
    return buf.getvalue()


def _cbz(path: Path, pages: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        for i in range(pages):
            archive.writestr(f"{i + 1:03d}.png", _png(i * 20))


def _enable(client: TestClient) -> None:
    assert client.patch("/api/import/config", json={"enabled": True}).status_code == 200


def _series_by_title(client: TestClient, title: str) -> dict[str, Any]:
    items = client.get("/api/series").json()["items"]
    return next(s for s in items if s["title"] == title)


def test_import_disabled_is_rejected(client: TestClient, tmp_path: Path) -> None:
    cbz = tmp_path / "incoming" / "Berserk.cbz"
    _cbz(cbz, 2)
    # disabled by default
    assert client.post("/api/import", json={"path": str(cbz), "kind": "manga"}).status_code == 400


def test_import_cbz_file_transcodes_to_avif(client: TestClient, tmp_path: Path) -> None:
    _enable(client)
    cbz = tmp_path / "incoming" / "Solo Leveling.cbz"
    _cbz(cbz, 3)

    assert client.post("/api/import", json={"path": str(cbz), "kind": "manga"}).status_code == 202
    queue.wait_idle()

    series = _series_by_title(client, "Solo Leveling")
    assert series["chapterCount"] == 1

    chapters = client.get(f"/api/series/{series['id']}/chapters").json()
    chapter_id = chapters[0]["chapters"][0]["id"]
    page = client.get(f"/api/chapters/{chapter_id}/pages/1")
    assert page.status_code == 200
    assert page.headers["content-type"] == "image/avif"  # re-encoded, not the source PNG

    # cover was warmed by the import (no /cover request made here)
    store = ThumbnailStore(tmp_path / "storage" / "thumbnails")
    assert store.exists(str(series["id"]), ThumbVariant.COVER)


def test_import_folder_with_multiple_chapters(client: TestClient, tmp_path: Path) -> None:
    _enable(client)
    root = tmp_path / "incoming" / "Berserk"
    _cbz(root / "Chapter 1.cbz", 2)
    _cbz(root / "Chapter 2.cbz", 2)

    assert client.post("/api/import", json={"path": str(root), "kind": "manga"}).status_code == 202
    queue.wait_idle()

    assert _series_by_title(client, "Berserk")["chapterCount"] == 2


def test_import_is_idempotent(client: TestClient, tmp_path: Path) -> None:
    _enable(client)
    cbz = tmp_path / "incoming" / "Frieren.cbz"
    _cbz(cbz, 2)
    body = {"path": str(cbz), "kind": "manga"}

    assert client.post("/api/import", json=body).status_code == 202
    queue.wait_idle()
    again = client.post("/api/import", json=body)
    assert again.status_code == 202
    queue.wait_idle()

    tasks = {t["id"]: t for t in client.get("/api/tasks").json()}
    assert tasks[again.json()["id"]]["result"] == {"booksImported": 0}  # already imported
    # exactly one Frieren series
    titles = [s["title"] for s in client.get("/api/series").json()["items"]]
    assert titles.count("Frieren") == 1


def test_import_applies_filename_pattern(client: TestClient, tmp_path: Path) -> None:
    _enable(client)
    assert client.patch(
        "/api/import/config", json={"filenamePattern": "{author} - {series} - c{chapter}"}
    ).status_code == 200
    root = tmp_path / "incoming" / "raw"  # folder name is ignored; the pattern names the series
    _cbz(root / "Kentaro Miura - Berserk - c001.cbz", 2)
    _cbz(root / "Kentaro Miura - Berserk - c002.cbz", 2)

    assert client.post("/api/import", json={"path": str(root), "kind": "manga"}).status_code == 202
    queue.wait_idle()

    series = _series_by_title(client, "Berserk")  # {series}, not the "raw" folder
    assert series["chapterCount"] == 2
    assert "Kentaro Miura" in series["authors"]  # {author} → credit
    numbers = sorted(
        c["number"]
        for group in client.get(f"/api/series/{series['id']}/chapters").json()
        for c in group["chapters"]
    )
    assert numbers == ["1", "2"]  # {chapter}


def test_import_bad_path_rejected(client: TestClient, tmp_path: Path) -> None:
    _enable(client)
    missing = client.post("/api/import", json={"path": str(tmp_path / "nope.cbz"), "kind": "manga"})
    assert missing.status_code == 400


def _cbz_bytes(pages: int) -> io.BytesIO:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as archive:
        for i in range(pages):
            archive.writestr(f"{i + 1:03d}.png", _png(i * 30))
    buf.seek(0)
    return buf


def test_upload_import_transcodes(client: TestClient, tmp_path: Path) -> None:
    _enable(client)
    resp = client.post(
        "/api/import/upload",
        files={"files": ("Chainsaw Man.cbz", _cbz_bytes(2), "application/zip")},
        data={"kind": "manga"},
    )
    assert resp.status_code == 202
    queue.wait_idle()

    series = _series_by_title(client, "Chainsaw Man")
    assert series["chapterCount"] == 1
    chapters = client.get(f"/api/series/{series['id']}/chapters").json()
    chapter_id = chapters[0]["chapters"][0]["id"]
    assert client.get(f"/api/chapters/{chapter_id}/pages/1").headers["content-type"] == "image/avif"
    store = ThumbnailStore(tmp_path / "storage" / "thumbnails")
    assert store.exists(str(series["id"]), ThumbVariant.COVER)


def test_upload_disabled_is_rejected(client: TestClient) -> None:
    resp = client.post(  # disabled by default
        "/api/import/upload",
        files={"files": ("X.cbz", _cbz_bytes(1), "application/zip")},
        data={"kind": "manga"},
    )
    assert resp.status_code == 400


def test_upload_bad_type_is_rejected(client: TestClient) -> None:
    _enable(client)
    resp = client.post(
        "/api/import/upload",
        files={"files": ("notes.txt", io.BytesIO(b"nope"), "text/plain")},
        data={"kind": "manga"},
    )
    assert resp.status_code == 400


def test_upload_oversize_is_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    _enable(client)
    from src.integrations import local_import

    monkeypatch.setattr(local_import, "_MAX_UPLOAD_BYTES", 16)  # tiny cap
    resp = client.post(
        "/api/import/upload",
        files={"files": ("Big.cbz", _cbz_bytes(2), "application/zip")},
        data={"kind": "manga"},
    )
    assert resp.status_code == 400


def test_upload_multiple_files_group_into_one_series(client: TestClient) -> None:
    _enable(client)
    resp = client.post(
        "/api/import/upload",
        files=[
            ("files", ("Berserk c001.cbz", _cbz_bytes(2), "application/zip")),
            ("files", ("Berserk c002.cbz", _cbz_bytes(2), "application/zip")),
        ],
        data={"kind": "manga"},
    )
    assert resp.status_code == 202
    queue.wait_idle()

    # the shared filename prefix names the one series; each uploaded file is a chapter
    series = _series_by_title(client, "Berserk")
    assert series["chapterCount"] == 2


def test_import_output_is_stored_cbz(client: TestClient, tmp_path: Path) -> None:
    _enable(client)
    cbz = tmp_path / "incoming" / "Dandadan.cbz"
    _cbz(cbz, 3)
    assert client.post("/api/import", json={"path": str(cbz), "kind": "manga"}).status_code == 202
    queue.wait_idle()

    # the imported book is stored as one .cbz written with ZIP_STORED (no compression —
    # the AVIF pages are already compressed)
    archives = list((tmp_path / "storage" / "imports").rglob("*.cbz"))
    assert len(archives) == 1
    with zipfile.ZipFile(archives[0]) as archive:
        infos = archive.infolist()
        assert len(infos) == 3
        assert all(info.filename.endswith(".avif") for info in infos)
        assert all(info.compress_type == zipfile.ZIP_STORED for info in infos)


def test_import_writes_portable_cover_avif(client: TestClient, tmp_path: Path) -> None:
    _enable(client)
    cbz = tmp_path / "incoming" / "Spy x Family.cbz"
    _cbz(cbz, 3)
    assert client.post("/api/import", json={"path": str(cbz), "kind": "manga"}).status_code == 202
    queue.wait_idle()

    series = _series_by_title(client, "Spy x Family")
    # a portable Cover.avif sits beside the imported book(s), AVIF-encoded
    cover = tmp_path / "storage" / "imports" / series["id"] / "Cover.avif"
    assert cover.is_file()
    assert b"ftyp" in cover.read_bytes()[:16]
    # ?size=detail serves that canonical cover
    detail = client.get(f"/api/series/{series['id']}/cover", params={"size": "detail"})
    assert detail.status_code == 200
    assert detail.headers["content-type"] == "image/avif"


def test_import_excludes_cover_file_from_pages(client: TestClient, tmp_path: Path) -> None:
    _enable(client)
    cbz = tmp_path / "incoming" / "Oshi no Ko.cbz"
    cbz.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(cbz, "w") as archive:
        archive.writestr("Cover.png", _png(10))  # a cover in the source — not a page
        archive.writestr("001.png", _png(20))
        archive.writestr("002.png", _png(30))
    assert client.post("/api/import", json={"path": str(cbz), "kind": "manga"}).status_code == 202
    queue.wait_idle()

    series = _series_by_title(client, "Oshi no Ko")
    chapters = client.get(f"/api/series/{series['id']}/chapters").json()
    chapter_id = chapters[0]["chapters"][0]["id"]
    detail = client.get(f"/api/chapters/{chapter_id}").json()
    assert detail["pageCount"] == 2  # Cover.png excluded from the pages
