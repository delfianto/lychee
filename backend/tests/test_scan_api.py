"""End-to-end library scan tests (create library → scan → reconcile)."""

import io
import zipfile
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.catalog.models import Chapter, Series
from src.media.thumbnails import ThumbnailStore, ThumbVariant
from src.progress.models import ReadingProgress
from src.tasks.queue import queue


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


def _scan(client: TestClient, library_id: str) -> dict[str, int]:
    """Trigger a background scan, wait for the worker (and thumbs task), return scan result."""
    resp = client.post(f"/api/libraries/{library_id}/scan")
    assert resp.status_code == 202
    queue.wait_idle(timeout=120.0)
    tasks = {t["id"]: t for t in client.get("/api/tasks").json()}
    result = tasks[resp.json()["id"]]["result"]
    assert result is not None
    return result


def _create_and_scan(client: TestClient, root: Path) -> tuple[str, dict[str, int]]:
    created = client.post(
        "/api/libraries", json={"name": "Test", "path": str(root), "kind": "manga"}
    )
    assert created.status_code == 201
    library_id = created.json()["id"]
    return library_id, _scan(client, library_id)


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

    again = _scan(client, library_id)
    assert again == {
        "seriesAdded": 0,
        "booksAdded": 0,
        "booksUpdated": 0,
        "booksRemoved": 0,
        "lycheeInfoApplied": 0,
        "lycheeInfoWarnings": [],
    }


def test_scan_soft_deletes_missing(client: TestClient, tmp_path: Path) -> None:
    root = _make_library(tmp_path)
    library_id, _ = _create_and_scan(client, root)

    (root / "Berserk" / "Vol. 01" / "Chapter 2.cbz").unlink()
    result = _scan(client, library_id)
    assert result["booksRemoved"] == 1

    series = {s["title"]: s for s in client.get("/api/series").json()["items"]}
    assert series["Berserk"]["chapterCount"] == 1


def test_rescan_after_title_change_keeps_one_series(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    root = _make_library(tmp_path)
    library_id, _ = _create_and_scan(client, root)
    before = len(client.get("/api/series").json()["items"])

    # Metadata (PART F/M1) may rename the display title; the folder path is the
    # identity, so a rescan must update the same series, not create a duplicate.
    series = db_session.scalars(select(Series).where(Series.title == "Berserk")).one()
    series.title = "Berserk (Deluxe)"
    db_session.commit()
    _scan(client, library_id)

    after = client.get("/api/series").json()["items"]
    assert len(after) == before  # no duplicate "Berserk"
    assert any(s["title"] == "Berserk (Deluxe)" for s in after)


def test_move_restore_preserves_reading_progress(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    root = tmp_path / "lib"
    _cbz(root / "Kagurabachi" / "ch1.cbz", 3)
    library_id, _ = _create_and_scan(client, root)

    series = db_session.scalars(select(Series).where(Series.title == "Kagurabachi")).one()
    chapter = db_session.scalars(select(Chapter).where(Chapter.series_id == series.id)).one()
    db_session.add(
        ReadingProgress(chapter_id=chapter.id, series_id=series.id, current_page=7, completed=True)
    )
    db_session.commit()

    # Move the file across two scans: remove → rescan (soft-delete + snapshot), then add
    # the identical content at a new name → rescan (restore by size+hash → re-apply progress).
    (root / "Kagurabachi" / "ch1.cbz").unlink()
    _scan(client, library_id)
    _cbz(root / "Kagurabachi" / "ch1_moved.cbz", 3)  # byte-identical → same size + xxh3 hash
    _scan(client, library_id)

    db_session.expire_all()
    restored = db_session.scalars(
        select(ReadingProgress)
        .join(Chapter, ReadingProgress.chapter_id == Chapter.id)
        .where(Chapter.series_id == series.id)
    ).all()
    assert len(restored) == 1
    assert (restored[0].current_page, restored[0].completed) == (7, True)


def test_scan_warms_series_covers(client: TestClient, tmp_path: Path) -> None:
    root = _make_library(tmp_path)
    _create_and_scan(client, root)

    # Covers are generated by the scan, not lazily on first /cover request.
    store = ThumbnailStore(tmp_path / "storage" / "thumbnails")
    for series in client.get("/api/series").json()["items"]:
        assert store.exists(series["id"], ThumbVariant.COVER)  # derived 320px grid thumbnail


def _make_gallery_library(tmp_path: Path) -> Path:
    root = tmp_path / "galleries"
    _image_dir(root / "Artist Name" / "Set A", 4)  # gallery (image dir) under an artist
    _cbz(root / "Artist Name" / "Set B.cbz", 3)  # gallery (archive) under the same artist
    _cbz(root / "Loose Gallery.cbz", 2)  # root-level one-shot — no artist
    return root


def _create_and_scan_gallery(client: TestClient, root: Path) -> tuple[str, dict[str, int]]:
    created = client.post(
        "/api/libraries", json={"name": "Art", "path": str(root), "kind": "gallery"}
    )
    assert created.status_code == 201
    library_id = created.json()["id"]
    return library_id, _scan(client, library_id)


def test_gallery_scan_groups_by_artist(client: TestClient, tmp_path: Path) -> None:
    root = _make_gallery_library(tmp_path)
    _, summary = _create_and_scan_gallery(client, root)
    assert summary["seriesAdded"] == 3  # Set A, Set B, Loose Gallery — each its own gallery

    series = {s["title"]: s for s in client.get("/api/series").json()["items"]}
    # Under an artist: "Artist — Works"; root loose archive keeps its stem.
    assert set(series) == {"Artist Name — Set A", "Artist Name — Set B", "Loose Gallery"}
    assert all(s["kind"] == "gallery" for s in series.values())
    # the two under "Artist Name" are credited to the artist; the loose one isn't
    assert series["Artist Name — Set A"]["artists"] == ["Artist Name"]
    assert series["Artist Name — Set B"]["artists"] == ["Artist Name"]
    assert series["Loose Gallery"]["artists"] == []

    # an auto Collection named after the artist holds exactly those two galleries
    collections = {c["name"]: c for c in client.get("/api/collections").json()}
    assert "Artist Name" in collections
    detail = client.get(f"/api/collections/{collections['Artist Name']['id']}").json()
    assert {s["title"] for s in detail["series"]} == {
        "Artist Name — Set A",
        "Artist Name — Set B",
    }


def test_gallery_rescan_is_idempotent(client: TestClient, tmp_path: Path) -> None:
    root = _make_gallery_library(tmp_path)
    library_id, _ = _create_and_scan_gallery(client, root)
    _scan(client, library_id)  # scan again — must not double credits/collections

    series = {s["title"]: s for s in client.get("/api/series").json()["items"]}
    assert series["Artist Name — Set A"]["artists"] == ["Artist Name"]  # not doubled
    named = [c for c in client.get("/api/collections").json() if c["name"] == "Artist Name"]
    assert len(named) == 1  # one collection, not one per scan
    detail = client.get(f"/api/collections/{named[0]['id']}").json()
    assert len(detail["series"]) == 2  # membership not duplicated


def test_gallery_scan_indexes_mov_only_set(client: TestClient, tmp_path: Path) -> None:
    """Video-only work folders (.mov) must still become series (not dropped)."""
    root = tmp_path / "galleries"
    set_dir = root / "Byoru" / "Dream Bride"
    set_dir.mkdir(parents=True)
    _ = (set_dir / "clip.mov").write_bytes(b"0" * 64)
    _create_and_scan_gallery(client, root)

    titles = {s["title"] for s in client.get("/api/series").json()["items"]}
    assert "Byoru — Dream Bride" in titles


def test_library_list_reports_series_count(client: TestClient, tmp_path: Path) -> None:
    root = _make_library(tmp_path)
    library_id, _ = _create_and_scan(client, root)

    libraries = {lib["id"]: lib for lib in client.get("/api/libraries").json()}
    assert libraries[library_id]["seriesCount"] == 2
    assert libraries[library_id]["lastScan"] is not None
