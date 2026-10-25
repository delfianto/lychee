"""The badge counts chapter/folder work, never parent coordinators or images."""

import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src.downloads.models import DownloadTask
from src.integrations.sync import SyncJobManager
from src.tasks import activity
from src.tasks.context import Operation, current_operation
from src.tasks.queue import queue
from src.tasks.tracker import TaskTracker, tracker

from tests.support import make_series
from tests.test_pipeline_operations import png


def test_counter_counts_chapters_not_duplicate_parent_downloads(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated = TaskTracker()
    monkeypatch.setattr(activity, "tracker", isolated)
    monkeypatch.setattr(activity, "sync_jobs", SyncJobManager())
    for index in range(28):
        isolated.start("download", f"Parent {index}")
    series = make_series(db_session, title="Counter")
    for status in ("queued", "queued", "downloading", "done", "failed", "paused", "cancelled"):
        db_session.add(DownloadTask(series_id=series.id, chapter_label=status, status=status))
    db_session.commit()
    assert client.get("/api/activity").json() == {
        "downloadChapters": 3,
        "syncJobs": 0,
        "otherJobs": 0,
        "total": 3,
    }
    row = db_session.query(DownloadTask).filter_by(status="downloading").one()
    row.status = "done"
    db_session.commit()
    assert client.get("/api/activity").json()["total"] == 2
    # Pausing removes queued work from the count; retrying restores it.
    row.status = "paused"
    db_session.commit()
    assert client.get("/api/activity").json()["total"] == 2
    row.status = "queued"
    db_session.commit()
    assert client.get("/api/activity").json()["total"] == 3


def test_counter_uses_folders_and_sync_children_without_counting_parents_twice(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated, jobs = TaskTracker(), SyncJobManager()
    monkeypatch.setattr(activity, "tracker", isolated)
    monkeypatch.setattr(activity, "sync_jobs", jobs)
    gallery = isolated.start("scan", "Gallery library")
    isolated.units(gallery, 4, "folder")
    library_job = jobs.create(kind="scan", title="Library", source="disk", status="running")
    library_job.task_id = gallery.id
    mdex = isolated.start("sync", "MangaDex")
    for status in ("running", "queued", "done", "failed", "cancelled", "paused"):
        job = jobs.create(kind="sync", title=status, source="MangaDex", status=status)
        job.task_id = mdex.id
    assert client.get("/api/activity").json()["syncJobs"] == 6
    isolated.units(gallery, 1, "folder")
    assert client.get("/api/activity").json()["total"] == 3
    jobs.control("pause", job_id=library_job.id)
    previous_library = jobs.create(
        kind="scan", title="Previous library", source="disk", status="done"
    )
    previous_library.task_id = gallery.id
    assert client.get("/api/activity").json()["total"] == 2
    gallery.status = "cancelling"
    assert client.get("/api/activity").json()["total"] == 3
    isolated.finish(gallery, cancelled=True)
    isolated.finish(mdex)
    assert client.get("/api/activity").json()["total"] == 0


def test_discovery_and_unowned_jobs_are_counted_without_reviving_finished_owners(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated, jobs = TaskTracker(), SyncJobManager()
    monkeypatch.setattr(activity, "tracker", isolated)
    monkeypatch.setattr(activity, "sync_jobs", jobs)
    planning = isolated.start("scan", "Discovering")
    jobs.create(kind="sync", title="Standalone", source="MangaDex", status="running")
    result = client.get("/api/activity").json()
    assert result["syncJobs"] == 1 and result["otherJobs"] == 1
    isolated.units(planning, 0, "folder")
    assert client.get("/api/activity").json()["total"] == 1
    isolated.finish(planning)


def test_gallery_counter_decreases_per_folder_only_after_its_last_thumbnail(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.catalog import media
    from src.core.config import settings
    from src.library import service

    root = tmp_path / "gallery"
    for name, count in (("Fast", 1), ("Slow", 2)):
        folder = root / "Artist" / name
        folder.mkdir(parents=True)
        for index in range(count):
            (folder / f"{index}.png").write_bytes(png())
    created = client.post(
        "/api/libraries", json={"name": "Gallery count", "path": str(root), "kind": "gallery"}
    )
    library_id = created.json()["id"]
    monkeypatch.setattr(settings, "encode_workers", 3)
    monkeypatch.setattr(service, "warm_library_covers", lambda *_: 0)
    remaining_one, release = threading.Event(), threading.Event()
    real_units = tracker.units

    def units(task, remaining, kind):
        real_units(task, remaining, kind)
        if remaining == 1 and kind == "folder":
            remaining_one.set()

    def thumbnail(session, _store, series_id, _index):
        from src.catalog.models import Series

        series = session.get(Series, series_id)
        assert series is not None
        session.commit()
        if "Slow" in series.title:
            assert release.wait(10)
        return True

    monkeypatch.setattr(tracker, "units", units)
    monkeypatch.setattr(media, "ensure_gallery_item_thumb", thumbnail)
    response = client.post(f"/api/libraries/{library_id}/scan")
    try:
        assert remaining_one.wait(10), "the fast folder must finish independently"
        result = client.get("/api/activity").json()
        assert result["syncJobs"] == 1 and result["total"] == 1
        task = next(
            task for task in client.get("/api/tasks").json() if task["id"] == response.json()["id"]
        )
        assert task["workUnits"] == 1 and task["status"] == "running"
    finally:
        release.set()
        queue.wait_idle()
    assert client.get("/api/activity").json()["total"] == 0


def test_folder_reports_do_not_require_a_background_operation() -> None:
    from src.tasks.context import report_work_units

    report_work_units(3, "folder")
    token = current_operation.set(Operation("unit-test", lambda: None, lambda *_: None))
    try:
        report_work_units(2, "folder")
    finally:
        current_operation.reset(token)


def test_sync_history_cap_keeps_every_active_job() -> None:
    jobs = SyncJobManager(max_keep=2)
    active = [jobs.create(kind="sync", title=str(index), source="MangaDex") for index in range(8)]
    for index in range(5):
        jobs.create(kind="sync", title=f"Finished {index}", source="MangaDex", status="done")
    snapshot = jobs.list_jobs()
    assert {job.id for job in snapshot if job.status == "queued"} == {job.id for job in active}
    assert len([job for job in snapshot if job.status == "done"]) == 2
