"""Tests for the download pipeline + Downloads API (fake provider, no network)."""

import io
import threading

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session
from src.downloads.provider import RemoteChapter, register_provider
from src.tasks.queue import queue

from tests.support import make_series


def _png() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (24, 32), (60, 90, 120)).save(buf, "PNG")
    return buf.getvalue()


class _FakeProvider:
    id = "fake"

    def list_chapters(self, provider_series_id: str, *, language: str = "en") -> list[RemoteChapter]:
        return [
            RemoteChapter("fc1", "1", 1, "First", "en"),
            RemoteChapter("fc2", "2", 1, None, "en"),
        ]

    def fetch_pages(self, chapter: RemoteChapter) -> list[bytes]:
        return [_png(), _png()]


register_provider(_FakeProvider())


def _linked_series(db_session: Session):
    series = make_series(db_session, title="Downloaded", kind="manga")
    series.provider = "fake"
    series.provider_series_id = "remote-1"
    db_session.commit()
    return series


def test_download_creates_chapters_and_avif_pages(
    client: TestClient, db_session: Session
) -> None:
    series = _linked_series(db_session)

    resp = client.post("/api/downloads", json={"seriesId": series.id})
    assert resp.status_code == 202
    queue.wait_idle()

    downloads = client.get("/api/downloads").json()
    assert len(downloads) == 2
    assert all(t["status"] == "done" for t in downloads)

    chapters = client.get(f"/api/series/{series.id}/chapters").json()
    numbers = [c["number"] for group in chapters for c in group["chapters"]]
    assert set(numbers) == {"1", "2"}

    # a downloaded page is served as AVIF
    chapter_id = chapters[0]["chapters"][0]["id"]
    page = client.get(f"/api/chapters/{chapter_id}/pages/1")
    assert page.status_code == 200
    assert page.headers["content-type"] == "image/avif"


def test_download_is_idempotent_and_listed(client: TestClient, db_session: Session) -> None:
    series = _linked_series(db_session)
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


def test_download_requires_provider(client: TestClient, db_session: Session) -> None:
    series = make_series(db_session, title="Unlinked")
    db_session.commit()
    assert client.post("/api/downloads", json={"seriesId": series.id}).status_code == 400


class _BlockingProvider:
    """Blocks inside fetch_pages until released, so a download stays mid-flight."""

    id = "blocking"

    def __init__(self) -> None:
        self.started = threading.Event()
        self.gate = threading.Event()

    def list_chapters(self, provider_series_id: str, *, language: str = "en") -> list[RemoteChapter]:
        return [RemoteChapter("bc1", "1", 1, None, "en")]

    def fetch_pages(self, chapter: RemoteChapter) -> list[bytes]:
        self.started.set()
        _ = self.gate.wait(timeout=5)
        return [_png(), _png()]


def test_download_row_visible_while_running(client: TestClient, db_session: Session) -> None:
    provider = _BlockingProvider()
    register_provider(provider)
    series = make_series(db_session, title="Blocking", kind="manga")
    series.provider = "blocking"
    series.provider_series_id = "remote-b"
    db_session.commit()

    assert client.post("/api/downloads", json={"seriesId": series.id}).status_code == 202
    assert provider.started.wait(2)  # worker began the (blocked) chapter fetch
    try:
        # the row is committed as "downloading" before the chapter finishes
        rows = client.get("/api/downloads").json()
        assert len(rows) == 1
        assert rows[0]["status"] == "downloading"
    finally:
        provider.gate.set()  # release the worker regardless of the assertions

    queue.wait_idle()
    assert client.get("/api/downloads").json()[0]["status"] == "done"


def test_delete_and_clear_completed(client: TestClient, db_session: Session) -> None:
    series = _linked_series(db_session)
    assert client.post("/api/downloads", json={"seriesId": series.id}).status_code == 202
    queue.wait_idle()
    tasks = client.get("/api/downloads").json()
    assert len(tasks) == 2

    assert client.delete(f"/api/downloads/{tasks[0]['id']}").status_code == 204
    assert len(client.get("/api/downloads").json()) == 1

    assert client.post("/api/downloads/clear-completed").status_code == 204
    assert client.get("/api/downloads").json() == []
