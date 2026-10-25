"""Tests for sync job logs, pause/cancel controls, worker limiters (1–10), and simultaneous execution."""

from __future__ import annotations

import io
import threading
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session
from src.catalog.models import Library, Series
from src.downloads.provider import RemoteChapter, register_provider
from src.integrations.sync import sync_jobs
from src.tasks.queue import queue


def _page_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color=(40, 80, 120)).save(buf, format="JPEG")
    return buf.getvalue()


class _SyncAndDownloadProvider:
    id = "simprov"

    def __init__(self) -> None:
        self.download_started = threading.Event()
        self.sync_started = threading.Event()
        self.release_download = threading.Event()
        self.fail_series_id: str | None = None

    def list_chapters(
        self, provider_series_id: str, *, language: str = "en"
    ) -> list[RemoteChapter]:
        self.sync_started.set()
        if provider_series_id == self.fail_series_id:
            raise RuntimeError("Upstream provider error 503")
        return [
            RemoteChapter(
                provider_chapter_id=f"{provider_series_id}-c1",
                number="1",
                volume=1,
                title="Chapter 1",
                language=language,
            ),
            RemoteChapter(
                provider_chapter_id=f"{provider_series_id}-c2",
                number="2",
                volume=1,
                title="Chapter 2",
                language=language,
            ),
        ]

    def fetch_pages(
        self, chapter: RemoteChapter, *, data_saver: bool = False, on_page=None
    ) -> list[bytes]:
        self.download_started.set()
        _ = self.release_download.wait(timeout=5.0)
        return [_page_bytes()]


def test_parallel_limiter_configs_and_validation(client: TestClient) -> None:
    assert client.get("/api/downloads/config").json() == {
        "parallelDownloads": 1,
        "autoClearCompleted": False,
    }
    assert client.patch("/api/downloads/config", json={"parallelDownloads": 4}).json() == {
        "parallelDownloads": 4,
        "autoClearCompleted": False,
    }
    assert client.patch("/api/downloads/config", json={"parallelDownloads": 0}).status_code == 422
    assert client.patch("/api/downloads/config", json={"parallelDownloads": 11}).status_code == 422

    sync_data = client.patch("/api/sync/config", json={"parallelSyncs": 5}).json()
    assert sync_data["parallelSyncs"] == 5
    assert client.patch("/api/sync/config", json={"parallelSyncs": 0}).status_code == 422
    assert client.patch("/api/sync/config", json={"parallelSyncs": 12}).status_code == 422


def test_sync_job_progress_errors_and_controls(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    provider = _SyncAndDownloadProvider()
    provider.fail_series_id = "bad-series"
    register_provider(provider)

    lib_dir = tmp_path / "scan_lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    # Create one valid series folder and one corrupt archive to trigger a scan indexing error.
    good_dir = lib_dir / "Good Manga"
    good_dir.mkdir()
    (good_dir / "001.jpg").write_bytes(_page_bytes())
    (lib_dir / "Corrupt.cbz").write_bytes(b"not a valid zip archive")

    lib = Library(name="Local Manga", path=str(lib_dir), kind="manga", enabled=True)
    db_session.add(lib)
    db_session.flush()

    s_ok = Series(
        library_id=lib.id,
        kind="manga",
        title="Pulled Manga",
        sort_title="pulled manga",
        path_rel="Pulled Manga",
        provider="simprov",
        provider_series_id="ok-series",
    )
    s_bad = Series(
        library_id=lib.id,
        kind="manga",
        title="Broken Manga",
        sort_title="broken manga",
        path_rel="Broken Manga",
        provider="simprov",
        provider_series_id="bad-series",
    )
    db_session.add_all([s_ok, s_bad])
    db_session.commit()

    _ = client.patch("/api/sync/config", json={"parallelSyncs": 2})
    assert client.post("/api/sync").status_code == 202
    queue.wait_idle()

    state = client.get("/api/sync").json()
    by_title = {job["title"]: job for job in state["jobs"]}
    assert by_title["Pulled Manga"]["status"] == "done"
    assert "Pulled from" in (by_title["Pulled Manga"]["detail"] or "")
    assert by_title["Broken Manga"]["status"] == "failed"
    assert "Upstream provider error 503" in (by_title["Broken Manga"]["error"] or "")

    # Scan library and verify scan job + corrupt file indexing error are logged.
    assert client.post(f"/api/libraries/{lib.id}/scan").status_code == 202
    queue.wait_idle()
    after_scan = client.get("/api/sync").json()
    scan_jobs = [j for j in after_scan["jobs"] if j["kind"] == "scan"]
    assert any(j["title"] == "Local Manga" and j["status"] == "done" for j in scan_jobs)
    assert any(j["title"] == "Corrupt.cbz" and j["status"] == "failed" for j in scan_jobs)

    # Test pause, resume, cancel, and clear-completed controls on sync jobs.
    queued = sync_jobs.create(
        kind="sync",
        title="Manual Job",
        source="MangaDex",
        status="queued",
        detail="Queued",
    )
    paused = client.post("/api/sync/control", json={"action": "pause", "jobId": queued.id}).json()
    assert next(j for j in paused["jobs"] if j["id"] == queued.id)["status"] == "paused"

    resumed = client.post("/api/sync/control", json={"action": "resume", "jobId": queued.id}).json()
    assert next(j for j in resumed["jobs"] if j["id"] == queued.id)["status"] == "queued"

    # Global pause / resume / cancel.
    assert client.post("/api/sync/control", json={"action": "pause-all"}).json()["paused"] is True
    assert client.post("/api/sync/control", json={"action": "resume-all"}).json()["paused"] is False
    cancelled = client.post("/api/sync/control", json={"action": "cancel-all"}).json()
    assert next(j for j in cancelled["jobs"] if j["id"] == queued.id)["status"] == "cancelled"

    cleared = client.post("/api/sync/control", json={"action": "clear-completed"}).json()
    assert cleared["jobs"] == []

    assert client.post("/api/sync/control", json={"action": "invalid"}).status_code == 400
    assert (
        client.post("/api/sync/control", json={"action": "pause", "jobId": "missing"}).status_code
        == 404
    )


def test_download_and_sync_run_simultaneously(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    provider = _SyncAndDownloadProvider()
    register_provider(provider)

    lib_dir = tmp_path / "dl_lib"
    lib_dir.mkdir(parents=True, exist_ok=True)
    lib = Library(name="Manga", path=str(lib_dir), kind="manga", enabled=True)
    db_session.add(lib)
    db_session.flush()

    series = Series(
        library_id=lib.id,
        kind="manga",
        title="Concurrent Series",
        sort_title="concurrent series",
        path_rel="Concurrent Series",
        provider="simprov",
        provider_series_id="conc-1",
    )
    db_session.add(series)
    db_session.commit()

    _ = client.patch("/api/downloads/config", json={"parallelDownloads": 2})

    # Start a download that blocks in fetch_pages until release_download is set.
    dl_resp = client.post("/api/downloads", json={"seriesId": series.id})
    assert dl_resp.status_code == 202
    assert provider.download_started.wait(timeout=5.0)

    # While the download is actively holding a download worker, start a sync job and verify
    # it runs and completes on the sync pool without waiting for the download!
    provider.sync_started.clear()
    sync_resp = client.post("/api/sync")
    assert sync_resp.status_code == 202
    assert provider.sync_started.wait(timeout=5.0)

    provider.release_download.set()
    queue.wait_idle()
