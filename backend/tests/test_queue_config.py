"""Worker preferences survive a fresh queue and restore before downloads resume."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from src import bootstrap
from src.core.persistence import database
from src.downloads import downloader
from src.media import encode_pool
from src.tasks import config
from src.tasks.models import TaskQueueConfig
from src.tasks.queue import TaskQueue, queue


def assert_limits(target: TaskQueue, downloads: int, syncs: int) -> None:
    assert target.download_workers == downloads
    assert target.sync_workers == syncs
    assert (
        target.download_limit.count
        == target.chapter_limit.count
        == target.file_limit.count
        == downloads
    )
    assert target.sync_limit.count == target.sync_item_limit.count == syncs


def test_preferences_persist_independently_and_restore_to_a_fresh_queue(
    client: TestClient, db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    encode_pool.configure_workers(2, 3)
    assert client.get("/api/downloads/config").json() == {"parallelDownloads": 1}
    assert client.get("/api/sync").json()["parallelSyncs"] == 1
    assert client.patch("/api/downloads/config", json={"parallelDownloads": 10}).status_code == 200
    assert client.patch("/api/sync/config", json={"parallelSyncs": 5}).status_code == 200
    assert_limits(queue, 10, 5)
    assert encode_pool.conversion_workers() == 2
    assert encode_pool.thumbnail_workers() == 3
    fresh = TaskQueue()
    assert_limits(fresh, 1, 1)
    monkeypatch.setattr(config, "queue", fresh)
    with Session(db_engine) as new_session:
        config.restore_queue(new_session)
        row = new_session.get(TaskQueueConfig, "default")
        assert row is not None
        assert (row.download_workers, row.sync_workers) == (10, 5)
    assert_limits(fresh, 10, 5)


def test_bootstrap_restores_all_budgets_before_download_recovery(
    client: TestClient, db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    client.patch("/api/downloads/config", json={"parallelDownloads": 7})
    client.patch("/api/sync/config", json={"parallelSyncs": 4})
    client.put(
        "/api/libraries/image-processing", json={"conversionWorkers": 6, "thumbnailWorkers": 2}
    )
    queue.set_download_workers(1)
    queue.set_sync_workers(1)
    encode_pool.configure_workers(1, 1)
    recovered = []

    def recover(session):
        assert_limits(queue, 7, 4)
        assert encode_pool.conversion_workers() == 6
        assert encode_pool.thumbnail_workers() == 2
        recovered.append(True)
        return 0

    monkeypatch.setattr(bootstrap, "run_migrations", lambda: None)
    monkeypatch.setattr(bootstrap, "run_seed", lambda: None)
    monkeypatch.setattr(database, "SessionLocal", sessionmaker(bind=db_engine))
    monkeypatch.setattr(downloader, "reclaim_orphaned_downloads", recover)
    bootstrap.bootstrap()
    bootstrap.bootstrap()  # Repeated startup must not reset saved preferences.
    assert recovered == [True, True]
    assert client.get("/api/downloads/config").json() == {"parallelDownloads": 7}
    assert client.get("/api/sync").json()["parallelSyncs"] == 4


def test_simultaneous_first_saves_do_not_duplicate_rows_or_lose_a_setting(
    client: TestClient, db_session: Session
) -> None:
    barrier = threading.Barrier(2)

    def save(path, body):
        barrier.wait(timeout=3)
        return client.patch(path, json=body)

    with ThreadPoolExecutor(max_workers=2) as callers:
        download = callers.submit(save, "/api/downloads/config", {"parallelDownloads": 8})
        sync = callers.submit(save, "/api/sync/config", {"parallelSyncs": 3})
        assert download.result(timeout=3).status_code == 200
        assert sync.result(timeout=3).status_code == 200
    assert_limits(queue, 8, 3)
    assert db_session.scalar(select(func.count()).select_from(TaskQueueConfig)) == 1
    row = db_session.get(TaskQueueConfig, "default")
    assert row is not None
    assert (row.download_workers, row.sync_workers) == (8, 3)
    client.patch("/api/downloads/config", json={"parallelDownloads": 2})
    assert client.get("/api/sync").json()["parallelSyncs"] == 3
    client.patch("/api/sync/config", json={"parallelSyncs": 6})
    assert client.get("/api/downloads/config").json() == {"parallelDownloads": 2}
    db_session.expire_all()
    assert db_session.scalar(select(func.count()).select_from(TaskQueueConfig)) == 1
    assert (row.download_workers, row.sync_workers) == (2, 6)


def test_unsaved_defaults_restore_to_one(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    fresh = TaskQueue(max_workers=9)
    monkeypatch.setattr(config, "queue", fresh)
    config.restore_queue(db_session)
    assert_limits(fresh, 1, 1)
    assert db_session.get(TaskQueueConfig, "default") is None


def test_failed_save_never_changes_live_limits(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail():
        raise RuntimeError("disk is full")

    monkeypatch.setattr(db_session, "commit", fail)
    with pytest.raises(RuntimeError, match="disk is full"):
        config.save_queue_workers(db_session, "download", 10)
    assert_limits(queue, 1, 1)
    db_session.rollback()
    assert db_session.get(TaskQueueConfig, "default") is None
