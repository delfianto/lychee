"""Tests for the download pipeline + Downloads API (fake provider, no network)."""

import io
import threading
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session
from src.downloads.downloader import chapter_path_rel
from src.downloads.provider import RemoteChapter, register_provider
from src.media.thumbnails import ThumbnailStore, ThumbVariant
from src.tasks.queue import queue

from tests.support import ensure_manga_library, make_series


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (24, 32), (60, 90, 120)).save(buf, "PNG")
    return buf.getvalue()


class _FakeProvider:
    id = "fake"

    def list_chapters(
        self, provider_series_id: str, *, language: str = "en"
    ) -> list[RemoteChapter]:
        return [
            RemoteChapter(
                "fc1",
                "1",
                1,
                "First",
                "en",
                group_name="Scan Team",
                published_at="2020-05-05T00:00:00+00:00",
            ),
            RemoteChapter("fc2", "2", 1, None, "en", group_name="Scan Team"),
        ]

    def fetch_pages(
        self, chapter: RemoteChapter, *, data_saver: bool = False, on_page=None
    ) -> list[bytes]:
        pages = [_png(), _png()]
        if on_page is not None:
            for i, _ in enumerate(pages, start=1):
                on_page(i, len(pages))
        return pages


register_provider(_FakeProvider())


def _linked_series(db_session: Session, manga_root: Path):
    ensure_manga_library(db_session, manga_root)
    series = make_series(db_session, title="Downloaded", kind="manga")
    series.provider = "fake"
    series.provider_series_id = "remote-1"
    db_session.commit()
    return series


def test_download_requires_manga_library(client: TestClient, db_session: Session) -> None:
    series = make_series(db_session, title="NoLib", kind="manga")
    series.provider = "fake"
    series.provider_series_id = "remote-x"
    db_session.commit()
    resp = client.post("/api/downloads", json={"seriesId": series.id})
    assert resp.status_code == 400
    assert "manga library" in resp.json()["error"]["message"].lower()


def test_download_creates_chapters_and_avif_pages(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    manga_root = tmp_path / "manga"
    series = _linked_series(db_session, manga_root)

    resp = client.post("/api/downloads", json={"seriesId": series.id})
    assert resp.status_code == 202
    queue.wait_idle()

    downloads = client.get("/api/downloads").json()
    assert len(downloads) == 2
    assert all(t["status"] == "done" for t in downloads)

    chapters = client.get(f"/api/series/{series.id}/chapters").json()
    numbers = [c["number"] for group in chapters for c in group["chapters"]]
    assert set(numbers) == {"1", "2"}
    groups = [c["group"] for group in chapters for c in group["chapters"]]
    assert "Scan Team" in groups  # scanlation group carried through from the feed

    # Human-readable layout under the manga library (not storage/downloads)
    assert (manga_root / "Downloaded" / "Vol.01" / "Ch.1 - First.cbz").is_file()
    assert (manga_root / "Downloaded" / "Vol.01" / "Ch.2.cbz").is_file()
    assert not (tmp_path / "storage" / "downloads").exists() or not any(
        (tmp_path / "storage" / "downloads").rglob("*.cbz")
    )

    # a downloaded page is served as AVIF
    chapter_id = next(c["id"] for group in chapters for c in group["chapters"] if c["id"])
    page = client.get(f"/api/chapters/{chapter_id}/pages/1")
    assert page.status_code == 200
    assert page.headers["content-type"] == "image/avif"


def test_download_warms_series_cover(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    manga_root = tmp_path / "manga"
    series = _linked_series(db_session, manga_root)
    assert client.post("/api/downloads", json={"seriesId": series.id}).status_code == 202
    queue.wait_idle()

    store = ThumbnailStore(tmp_path / "storage" / "thumbnails")
    assert store.exists(series.id, ThumbVariant.COVER)
    assert (manga_root / "Downloaded" / "Cover.avif").is_file()


def test_download_is_idempotent_and_listed(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    series = _linked_series(db_session, tmp_path / "manga")
    assert client.post("/api/downloads", json={"seriesId": series.id}).status_code == 202
    queue.wait_idle()

    again = client.post("/api/downloads", json={"seriesId": series.id})
    assert again.status_code == 202
    queue.wait_idle()
    tasks = {t["id"]: t for t in client.get("/api/tasks").json()}
    assert tasks[again.json()["id"]]["result"] == {"downloaded": 0}  # both already present

    listed = client.get("/api/downloads").json()
    assert len(listed) == 2
    assert listed[0]["series"]["title"] == "Downloaded"


def test_download_requires_provider(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    ensure_manga_library(db_session, tmp_path / "manga")
    series = make_series(db_session, title="Unlinked")
    db_session.commit()
    assert client.post("/api/downloads", json={"seriesId": series.id}).status_code == 400


class _BlockingProvider:
    """Blocks inside fetch_pages until released, so a download stays mid-flight."""

    id = "blocking"

    def __init__(self) -> None:
        self.started = threading.Event()
        self.gate = threading.Event()

    def list_chapters(
        self, provider_series_id: str, *, language: str = "en"
    ) -> list[RemoteChapter]:
        return [RemoteChapter("bc1", "1", 1, None, "en")]

    def fetch_pages(
        self, chapter: RemoteChapter, *, data_saver: bool = False, on_page=None
    ) -> list[bytes]:
        self.started.set()
        _ = self.gate.wait(timeout=5)
        pages = [_png(), _png()]
        if on_page is not None:
            for i, _ in enumerate(pages, start=1):
                on_page(i, len(pages))
        return pages


def test_download_row_visible_while_running(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    provider = _BlockingProvider()
    register_provider(provider)
    ensure_manga_library(db_session, tmp_path / "manga")
    series = make_series(db_session, title="Blocking", kind="manga")
    series.provider = "blocking"
    series.provider_series_id = "remote-b"
    db_session.commit()

    assert client.post("/api/downloads", json={"seriesId": series.id}).status_code == 202
    assert provider.started.wait(2)  # worker began the (blocked) chapter fetch
    try:
        rows = client.get("/api/downloads").json()
        assert len(rows) == 1
        assert rows[0]["status"] == "downloading"
        assert rows[0]["phase"] == "fetching"
    finally:
        provider.gate.set()  # release the worker regardless of the assertions

    queue.wait_idle()
    done = client.get("/api/downloads").json()[0]
    assert done["status"] == "done"
    assert done.get("phase") in (None, "")


class _GatedMultiProvider:
    """Two chapters; blocks inside the first chapter's fetch so the second sits queued."""

    id = "gated"

    def __init__(self) -> None:
        self.started = threading.Event()
        self.gate = threading.Event()

    def list_chapters(
        self, provider_series_id: str, *, language: str = "en"
    ) -> list[RemoteChapter]:
        return [RemoteChapter("gc1", "1", 1, None, "en"), RemoteChapter("gc2", "2", 1, None, "en")]

    def fetch_pages(
        self, chapter: RemoteChapter, *, data_saver: bool = False, on_page=None
    ) -> list[bytes]:
        if chapter.provider_chapter_id == "gc1":
            self.started.set()
            _ = self.gate.wait(timeout=5)
        pages = [_png(), _png()]
        if on_page is not None:
            for i, _ in enumerate(pages, start=1):
                on_page(i, len(pages))
        return pages


def test_pause_holds_queued_chapter_then_resume_downloads_it(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    provider = _GatedMultiProvider()
    register_provider(provider)
    ensure_manga_library(db_session, tmp_path / "manga")
    series = make_series(db_session, title="Gated", kind="manga")
    series.provider = "gated"
    series.provider_series_id = "remote-g"
    db_session.commit()

    assert client.post("/api/downloads", json={"seriesId": series.id}).status_code == 202
    assert provider.started.wait(2)
    try:
        rows = {r["chapter"]: r for r in client.get("/api/downloads").json()}
        assert rows["Ch. 1"]["status"] == "downloading"
        assert rows["Ch. 2"]["status"] == "queued"

        paused = client.post(f"/api/downloads/{rows['Ch. 2']['id']}/pause")
        assert paused.status_code == 200
        assert {r["chapter"]: r["status"] for r in paused.json()}["Ch. 2"] == "paused"
    finally:
        provider.gate.set()
    queue.wait_idle()

    held = {r["chapter"]: r["status"] for r in client.get("/api/downloads").json()}
    assert held == {"Ch. 1": "done", "Ch. 2": "paused"}

    ch2_id = next(r["id"] for r in client.get("/api/downloads").json() if r["chapter"] == "Ch. 2")
    assert client.post(f"/api/downloads/{ch2_id}/resume").status_code == 200
    queue.wait_idle()

    done = {r["chapter"]: r["status"] for r in client.get("/api/downloads").json()}
    assert done == {"Ch. 1": "done", "Ch. 2": "done"}


def test_pause_rejects_non_queued_download(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    series = _linked_series(db_session, tmp_path / "manga")
    assert client.post("/api/downloads", json={"seriesId": series.id}).status_code == 202
    queue.wait_idle()
    done_id = client.get("/api/downloads").json()[0]["id"]
    assert client.post(f"/api/downloads/{done_id}/pause").status_code == 400
    assert client.post(f"/api/downloads/{done_id}/resume").status_code == 400


def test_delete_and_clear_completed(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    series = _linked_series(db_session, tmp_path / "manga")
    assert client.post("/api/downloads", json={"seriesId": series.id}).status_code == 202
    queue.wait_idle()
    tasks = client.get("/api/downloads").json()
    assert len(tasks) == 2

    assert client.delete(f"/api/downloads/{tasks[0]['id']}").status_code == 204
    assert len(client.get("/api/downloads").json()) == 1

    assert client.post("/api/downloads/clear-completed").status_code == 204
    assert client.get("/api/downloads").json() == []


def test_bulk_pause_all_and_resume_all(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    provider = _GatedMultiProvider()
    register_provider(provider)
    ensure_manga_library(db_session, tmp_path / "manga")
    series = make_series(db_session, title="BulkPause", kind="manga")
    series.provider = "gated"
    series.provider_series_id = "remote-bp"
    db_session.commit()

    assert client.post("/api/downloads", json={"seriesId": series.id}).status_code == 202
    assert provider.started.wait(2)
    try:
        paused = client.post("/api/downloads", json={"action": "pause-all"})
        assert paused.status_code == 200
        by_ch = {r["chapter"]: r["status"] for r in paused.json()}
        assert by_ch["Ch. 1"] == "downloading"
        assert by_ch["Ch. 2"] == "paused"
    finally:
        provider.gate.set()
    queue.wait_idle()

    held = {r["chapter"]: r["status"] for r in client.get("/api/downloads").json()}
    assert held["Ch. 1"] == "done"
    assert held["Ch. 2"] == "paused"

    resumed = client.post("/api/downloads", json={"action": "resume-all"})
    assert resumed.status_code == 200
    queue.wait_idle()
    done = {r["chapter"]: r["status"] for r in client.get("/api/downloads").json()}
    assert done == {"Ch. 1": "done", "Ch. 2": "done"}


def test_bulk_cancel_all_clears_queued(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    provider = _GatedMultiProvider()
    register_provider(provider)
    ensure_manga_library(db_session, tmp_path / "manga")
    series = make_series(db_session, title="BulkCancel", kind="manga")
    series.provider = "gated"
    series.provider_series_id = "remote-bc"
    db_session.commit()

    assert client.post("/api/downloads", json={"seriesId": series.id}).status_code == 202
    assert provider.started.wait(2)
    try:
        cancelled = client.post("/api/downloads", json={"action": "cancel-all"})
        assert cancelled.status_code == 200
        statuses = {r["status"] for r in cancelled.json()}
        assert "queued" not in statuses
        assert "paused" not in statuses
    finally:
        provider.gate.set()
    queue.wait_idle()
    remaining = client.get("/api/downloads").json()
    assert all(r["status"] != "queued" for r in remaining)


def test_reclaim_orphaned_downloading(db_session: Session, tmp_path: Path) -> None:
    from src.downloads.downloader import reclaim_orphaned_downloads
    from src.downloads.models import DownloadTask

    series = _linked_series(db_session, tmp_path / "manga")
    row = DownloadTask(
        series_id=series.id,
        chapter_label="Ch. 1",
        status="downloading",
        progress=40,
        phase="encoding",
        detail="3/10",
        provider="fake",
    )
    db_session.add(row)
    db_session.commit()

    assert reclaim_orphaned_downloads(db_session) == 1
    db_session.refresh(row)
    assert row.status == "queued"
    assert row.progress == 0
    assert row.phase is None


def test_chapter_path_rel_human_readable(db_session: Session) -> None:
    series = make_series(db_session, title="My: Cool/Manga?", kind="manga")
    remote = RemoteChapter("x", "10.5", 2, "Finale", "en")
    rel = chapter_path_rel(series, remote)
    assert rel == "My CoolManga/Vol.02/Ch.10.5 - Finale.cbz"
