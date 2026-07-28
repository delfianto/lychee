"""lychee.info sidecar discovered + applied during a library scan (notes/decisions/20-lychee-info-metadata.md)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.catalog.models import Series
from src.ingest.lychee_info import LYCHEE_INFO_FILENAME
from src.tasks.queue import queue


def _cbz(path: Path) -> None:
    import zipfile

    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("001.png", b"not a real png, container open failure is fine here")


def _write_info(series_dir: Path, text: str) -> None:
    series_dir.mkdir(parents=True, exist_ok=True)
    (series_dir / LYCHEE_INFO_FILENAME).write_text(text)


def _scan(client: TestClient, library_id: str) -> dict[str, Any]:
    resp = client.post(f"/api/libraries/{library_id}/scan")
    assert resp.status_code == 202
    queue.wait_idle(timeout=120.0)
    tasks = {t["id"]: t for t in client.get("/api/tasks").json()}
    result = tasks[resp.json()["id"]]["result"]
    assert result is not None
    return result


_INFO_V1 = """
schema: 1
kind: manga
title: "Applied Title"
contentRating: suggestive
tags:
  genre: [horror]
"""


def test_scan_applies_lychee_info_at_series_folder(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "lib"
    _cbz(root / "Some Manga" / "ch1.cbz")
    _write_info(root / "Some Manga", _INFO_V1)

    created = client.post("/api/libraries", json={"name": "T", "path": str(root), "kind": "manga"})
    library_id = created.json()["id"]
    result = _scan(client, library_id)

    assert result["lycheeInfoApplied"] == 1
    assert result["lycheeInfoWarnings"] == []

    series = client.get("/api/series").json()["items"][0]
    assert series["title"] == "Applied Title"
    assert series["contentRating"] == "suggestive"
    assert "horror" in {t["id"] for t in series["tags"]}


def test_scan_skips_reapply_when_file_unchanged(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    root = tmp_path / "lib"
    _cbz(root / "Some Manga" / "ch1.cbz")
    _write_info(root / "Some Manga", _INFO_V1)

    created = client.post("/api/libraries", json={"name": "T", "path": str(root), "kind": "manga"})
    library_id = created.json()["id"]
    _scan(client, library_id)

    # Manually override the applied title to prove a second, unchanged-file scan
    # doesn't stomp it again (the hash gate short-circuits before re-applying).
    series = db_session.scalars(select(Series).where(Series.title == "Applied Title")).one()
    series.title = "Manually Renamed"
    db_session.commit()

    result = _scan(client, library_id)
    assert result["lycheeInfoApplied"] == 0

    db_session.expire_all()
    series = db_session.get(Series, series.id)
    assert series is not None
    assert series.title == "Manually Renamed"


def test_scan_reapplies_after_file_edited(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "lib"
    _cbz(root / "Some Manga" / "ch1.cbz")
    _write_info(root / "Some Manga", _INFO_V1)

    created = client.post("/api/libraries", json={"name": "T", "path": str(root), "kind": "manga"})
    library_id = created.json()["id"]
    _scan(client, library_id)

    _write_info(root / "Some Manga", _INFO_V1.replace("Applied Title", "Edited Title"))
    result = _scan(client, library_id)

    assert result["lycheeInfoApplied"] == 1
    series = client.get("/api/series").json()["items"][0]
    assert series["title"] == "Edited Title"


def test_scan_malformed_lychee_info_does_not_fail_scan(client: TestClient, tmp_path: Path) -> None:
    root = tmp_path / "lib"
    _cbz(root / "Some Manga" / "ch1.cbz")
    _write_info(root / "Some Manga", "schema: 1\nkind: manga\nfooBar: 1\n")

    created = client.post("/api/libraries", json={"name": "T", "path": str(root), "kind": "manga"})
    library_id = created.json()["id"]
    result = _scan(client, library_id)

    assert result["seriesAdded"] == 1  # series still indexed normally
    assert result["lycheeInfoApplied"] == 0
    assert len(result["lycheeInfoWarnings"]) == 1

    # Still malformed on the next scan → warns again (not silently suppressed).
    result = _scan(client, library_id)
    assert len(result["lycheeInfoWarnings"]) == 1


def test_scan_gallery_applies_lychee_info_per_work_folder(
    client: TestClient, tmp_path: Path
) -> None:
    root = tmp_path / "galleries"
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (10, 10)).save(buf, "PNG")
    work_dir = root / "Artist Name" / "Set A"
    work_dir.mkdir(parents=True)
    _ = (work_dir / "001.png").write_bytes(buf.getvalue())
    _write_info(
        work_dir,
        """
schema: 1
kind: gallery
crossovers:
  - series: "Some Franchise"
    characters: [Alice]
""",
    )

    created = client.post(
        "/api/libraries", json={"name": "Art", "path": str(root), "kind": "gallery"}
    )
    library_id = created.json()["id"]
    result = _scan(client, library_id)

    assert result["lycheeInfoApplied"] == 1
    series = client.get("/api/series").json()["items"][0]
    assert series["source"] == "Some Franchise"
    assert series["characters"] == ["Alice"]
