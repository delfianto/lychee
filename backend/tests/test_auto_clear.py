"""Auto-clear is persisted, independent, success-only, and owns complete pipelines."""

import io
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session
from src.catalog.models import Book, Chapter
from src.downloads.models import DownloadTask
from src.downloads.provider import RemoteChapter, register_provider
from src.integrations.sync import sync_jobs
from src.tasks import config
from src.tasks.context import Operation, current_operation
from src.tasks.queue import TaskQueue, queue

from tests.support import ensure_manga_library, make_series


def test_settings_are_independent_and_survive_worker_saves_and_restart(
    client: TestClient, db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert client.get("/api/downloads/config").json()["autoClearCompleted"] is False
    assert client.get("/api/sync").json()["autoClearCompleted"] is False
    client.patch("/api/downloads/config", json={"parallelDownloads": 7, "autoClearCompleted": True})
    assert client.get("/api/sync").json()["autoClearCompleted"] is False
    client.patch("/api/sync/config", json={"parallelSyncs": 3, "autoClearCompleted": True})
    client.put(
        "/api/libraries/workers",
        json={
            "downloadWorkers": 8,
            "scanMetadataWorkers": 4,
            "conversionWorkers": 1,
            "thumbnailWorkers": 1,
        },
    )
    fresh = TaskQueue()
    monkeypatch.setattr(config, "queue", fresh)
    with Session(db_engine) as session:
        config.restore_queue(session)
    assert fresh.auto_clear_downloads and fresh.auto_clear_syncs
    assert (fresh.download_workers, fresh.sync_workers) == (8, 4)


def test_enabling_clears_only_successful_download_rows(
    client: TestClient, db_session: Session
) -> None:
    series = make_series(db_session, title="Auto clear")
    for status in ("done", "failed", "cancelled", "paused", "queued", "downloading"):
        db_session.add(DownloadTask(series_id=series.id, chapter_label=status, status=status))
    db_session.commit()
    response = client.patch("/api/downloads/config", json={"autoClearCompleted": True})
    assert response.status_code == 200 and response.json()["parallelDownloads"] == 1
    assert {row["status"] for row in client.get("/api/downloads").json()} == {
        "failed",
        "cancelled",
        "paused",
        "queued",
        "downloading",
    }
    assert (
        client.patch("/api/downloads/config", json={"autoClearCompleted": False}).status_code == 200
    )
    db_session.add(DownloadTask(series_id=series.id, chapter_label="new", status="done"))
    db_session.commit()
    config.auto_clear_downloads(db_session)
    assert db_session.scalar(select(DownloadTask).where(DownloadTask.status == "done")) is not None


@pytest.mark.parametrize("path", ["/api/downloads/config", "/api/sync/config"])
def test_auto_clear_requires_boolean(client: TestClient, path: str) -> None:
    assert client.patch(path, json={"autoClearCompleted": "true"}).status_code == 422


def test_failed_save_does_not_clear_history_or_apply_settings(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    series = make_series(db_session, title="Auto clear")
    task = DownloadTask(series_id=series.id, chapter_label="done", status="done")
    db_session.add(task)
    db_session.commit()
    task_id = task.id

    def fail():
        raise RuntimeError("commit failed")

    monkeypatch.setattr(db_session, "commit", fail)
    with pytest.raises(RuntimeError, match="commit failed"):
        config.save_queue_workers(db_session, "download", None, auto_clear_completed=True)
    db_session.rollback()
    assert not queue.auto_clear_downloads
    assert db_session.get(DownloadTask, task_id) is not None


def test_sync_auto_clear_preserves_errors_and_retains_scan_until_all_stages_finish(
    client: TestClient,
) -> None:
    for status in ("done", "failed", "cancelled", "paused", "running"):
        sync_jobs.create(kind="sync", title=status, source="MangaDex", status=status)
    response = client.patch("/api/sync/config", json={"autoClearCompleted": True})
    assert response.status_code == 200
    assert {job["status"] for job in response.json()["jobs"]} == {
        "failed",
        "cancelled",
        "paused",
        "running",
    }
    completed = sync_jobs.create(kind="sync", title="Later", source="MangaDex")
    sync_jobs.update(completed.id, status="done")
    assert completed.id not in {job.id for job in sync_jobs.list_jobs()}

    operation = Operation("owner", lambda: None, lambda *_: None)
    token = current_operation.set(operation)
    try:
        scan = sync_jobs.create(kind="scan", title="Index and thumbnails", source="Library")
        sync_jobs.update(scan.id, status="done")
        assert scan.id in {job.id for job in sync_jobs.list_jobs()}
        for finalize in operation.finalizers:
            finalize("done")
        assert scan.id not in {job.id for job in sync_jobs.list_jobs()}
    finally:
        current_operation.reset(token)

    client.patch("/api/sync/config", json={"autoClearCompleted": False})
    retained = sync_jobs.create(kind="sync", title="Retained", source="MangaDex", status="done")
    assert retained.id in {job.id for job in sync_jobs.list_jobs()}


@pytest.mark.parametrize("disable_before_done", [False, True])
def test_download_clears_after_thumbnails_without_a_browser(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    disable_before_done: bool,
) -> None:
    started, release = threading.Event(), threading.Event()

    class Provider:
        id = "auto-clear-test"

        def list_chapters(self, *args, **kwargs):
            return [RemoteChapter("chapter-id", "1", None, None, "en")]

        def fetch_pages(self, *args, **kwargs):
            buf = io.BytesIO()
            Image.new("RGB", (16, 24), (10, 20, 30)).save(buf, "PNG")
            return [buf.getvalue()]

    def thumbnail(*args, **kwargs):
        started.set()
        assert release.wait(10)
        return True

    monkeypatch.setattr("src.downloads.downloader.generate_series_cover", thumbnail)
    register_provider(Provider())
    ensure_manga_library(db_session, tmp_path / "manga")
    series = make_series(db_session, title="Auto clear")
    series.provider, series.provider_series_id = Provider.id, "remote"
    db_session.commit()
    assert (
        client.patch("/api/downloads/config", json={"autoClearCompleted": True}).status_code == 200
    )
    try:
        assert client.post("/api/downloads", json={"seriesId": series.id}).status_code == 202
        assert started.wait(10)
        rows = client.get("/api/downloads").json()
        assert len(rows) == 1 and rows[0]["status"] == "downloading"
        if disable_before_done:
            client.patch("/api/downloads/config", json={"autoClearCompleted": False})
    finally:
        release.set()
        queue.wait_idle()
    rows = client.get("/api/downloads").json()
    assert len(rows) == int(disable_before_done)
    if rows:
        assert rows[0]["status"] == "done"
    chapter = db_session.scalar(select(Chapter).where(Chapter.series_id == series.id))
    assert chapter is not None
    book = db_session.get(Book, chapter.book_id)
    assert book is not None
    assert client.get(f"/api/chapters/{chapter.id}/pages/1").status_code == 200
