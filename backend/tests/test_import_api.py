"""End-to-end local import tests (enable → import file/folder → transcoded AVIF)."""

import io
import zipfile
from pathlib import Path

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


def _series_by_title(client: TestClient, title: str) -> dict[str, object]:
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


def test_import_bad_path_rejected(client: TestClient, tmp_path: Path) -> None:
    _enable(client)
    missing = client.post("/api/import", json={"path": str(tmp_path / "nope.cbz"), "kind": "manga"})
    assert missing.status_code == 400
