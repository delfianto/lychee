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
    assert target.file_limit.count == downloads
    assert target.io_limit.count == syncs
    assert target.chapter_limit.count == 10
    assert target.fetch_limit.count == 1


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


def test_library_workers_save_all_limits_and_restore_them(
    client: TestClient, db_engine: Engine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.media import processing

    client.patch("/api/downloads/config", json={"parallelDownloads": 7})
    client.patch("/api/sync/config", json={"parallelSyncs": 3})
    client.put(
        "/api/libraries/image-processing", json={"conversionWorkers": 4, "thumbnailWorkers": 2}
    )
    url = "/api/libraries/workers"
    initial = client.get(url).json()
    assert (
        initial.items()
        >= {
            "downloadWorkers": 7,
            "scanMetadataWorkers": 3,
            "conversionWorkers": 4,
            "thumbnailWorkers": 2,
        }.items()
    )
    values = {
        "downloadWorkers": 10,
        "scanMetadataWorkers": 6,
        "conversionWorkers": 12,
        "thumbnailWorkers": 5,
    }
    response = client.put(url, json=values)
    assert response.status_code == 200
    assert response.json().items() >= values.items()
    assert_limits(queue, 10, 6)
    assert encode_pool.conversion_workers() == 12
    assert encode_pool.thumbnail_workers() == 5
    fresh = TaskQueue()
    monkeypatch.setattr(config, "queue", fresh)
    encode_pool.configure_workers(1, 1)
    with Session(db_engine) as session:
        config.restore_queue(session)
        processing.configure_processing(session)
    assert_limits(fresh, 10, 6)
    assert encode_pool.conversion_workers() == 12
    assert encode_pool.thumbnail_workers() == 5


@pytest.mark.parametrize(
    "field,max_value",
    [
        ("downloadWorkers", 10),
        ("scanMetadataWorkers", 10),
        ("conversionWorkers", 64),
        ("thumbnailWorkers", 64),
    ],
)
@pytest.mark.parametrize("value", [0, 1.5, None, True, "4", "over_max"])
def test_library_workers_reject_invalid_budgets(
    client: TestClient, field, max_value, value
) -> None:
    initial = client.get("/api/libraries/workers").json()
    body = {
        "downloadWorkers": 4,
        "scanMetadataWorkers": 3,
        "conversionWorkers": 6,
        "thumbnailWorkers": 2,
        field: max_value + 1 if value == "over_max" else value,
    }
    assert client.put("/api/libraries/workers", json=body).status_code == 422
    assert client.get("/api/libraries/workers").json() == initial
    assert_limits(queue, initial["downloadWorkers"], initial["scanMetadataWorkers"])
    assert encode_pool.conversion_workers() == initial["conversionWorkers"]
    assert encode_pool.thumbnail_workers() == initial["thumbnailWorkers"]


@pytest.mark.parametrize("existing", [False, True])
def test_failed_combined_save_rolls_back_all_rows_and_applies_no_limits(
    client: TestClient,
    db_session: Session,
    db_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
    existing: bool,
) -> None:
    from src.media.models import ImageProcessingConfig
    from src.tasks.schema import WorkerSettingsUpdate

    if existing:
        config.save_worker_settings(
            db_session,
            WorkerSettingsUpdate(
                download_workers=4,
                scan_metadata_workers=3,
                conversion_workers=6,
                thumbnail_workers=2,
            ),
        )
    before = config.get_worker_settings(db_session)

    def fail():
        db_session.flush()  # Exercise rollback after both inserts/updates reached the database.
        raise RuntimeError("disk is full")

    monkeypatch.setattr(db_session, "commit", fail)
    with pytest.raises(RuntimeError, match="disk is full"):
        config.save_worker_settings(
            db_session,
            WorkerSettingsUpdate(
                download_workers=7,
                scan_metadata_workers=5,
                conversion_workers=12,
                thumbnail_workers=4,
            ),
        )
    assert_limits(queue, before.download_workers, before.scan_metadata_workers)
    assert encode_pool.conversion_workers() == before.conversion_workers
    assert encode_pool.thumbnail_workers() == before.thumbnail_workers
    db_session.rollback()
    with Session(db_engine) as session:
        row = session.get(TaskQueueConfig, "default")
        image = session.get(ImageProcessingConfig, "default")
        if existing:
            assert row is not None and image is not None
            assert (
                row.download_workers,
                row.sync_workers,
                image.conversion_workers,
                image.thumbnail_workers,
            ) == (4, 3, 6, 2)
        else:
            assert row is image is None


def test_simultaneous_combined_saves_persist_one_complete_configuration(
    client: TestClient, db_session: Session
) -> None:
    from src.media.models import ImageProcessingConfig

    barrier = threading.Barrier(2)
    configurations = [
        {
            "downloadWorkers": 4,
            "scanMetadataWorkers": 3,
            "conversionWorkers": 6,
            "thumbnailWorkers": 2,
        },
        {
            "downloadWorkers": 8,
            "scanMetadataWorkers": 5,
            "conversionWorkers": 12,
            "thumbnailWorkers": 4,
        },
    ]

    def save(body):
        barrier.wait(timeout=3)
        return client.put("/api/libraries/workers", json=body)

    with ThreadPoolExecutor(max_workers=2) as callers:
        results = list(callers.map(save, configurations))
    assert all(result.status_code == 200 for result in results)
    final = client.get("/api/libraries/workers").json()
    assert any(final.items() >= value.items() for value in configurations)
    assert_limits(queue, final["downloadWorkers"], final["scanMetadataWorkers"])
    assert encode_pool.conversion_workers() == final["conversionWorkers"]
    assert encode_pool.thumbnail_workers() == final["thumbnailWorkers"]
    assert db_session.scalar(select(func.count()).select_from(TaskQueueConfig)) == 1
    assert db_session.scalar(select(func.count()).select_from(ImageProcessingConfig)) == 1


def test_auto_detection_refreshes_cpu_recommendations_without_persisting_changes(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.media import processing
    from src.media.models import ImageProcessingConfig

    monkeypatch.setattr(processing.os, "process_cpu_count", lambda: 32)
    initial = client.get("/api/libraries/workers").json()
    monkeypatch.setattr(processing.os, "process_cpu_count", lambda: 16)
    detected = client.get("/api/libraries/workers").json()
    assert detected["cpuThreads"] == 16
    assert detected["recommendedConversionWorkers"] == 8
    assert detected["recommendedThumbnailWorkers"] == 2
    for field in (
        "downloadWorkers",
        "scanMetadataWorkers",
        "conversionWorkers",
        "thumbnailWorkers",
    ):
        assert detected[field] == initial[field]
    assert db_session.get(TaskQueueConfig, "default") is None
    assert db_session.get(ImageProcessingConfig, "default") is None
