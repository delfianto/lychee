"""Persistent independent CPU budgets, including restore and strict API validation."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src.core.config import settings
from src.media import encode_pool, processing
from src.tasks.queue import queue

URL = "/api/libraries/image-processing"


def test_independent_worker_settings_persist_and_restore(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(processing.os, "process_cpu_count", lambda: 32)
    monkeypatch.setattr(settings, "encode_workers", 1)
    assert client.get(URL).json() == {
        "conversionWorkers": 1,
        "thumbnailWorkers": 1,
        "cpuThreads": 32,
        "recommendedConversionWorkers": 16,
        "recommendedThumbnailWorkers": 4,
    }
    queue.set_download_workers(10)
    response = client.put(URL, json={"conversionWorkers": 3, "thumbnailWorkers": 2})
    assert response.status_code == 200
    assert encode_pool.conversion_workers() == 3
    assert encode_pool.thumbnail_workers() == 2
    assert queue.download_workers == 10
    assert client.get(URL).json()["conversionWorkers"] == 3
    encode_pool.configure_workers(None, None)
    assert encode_pool.conversion_workers() == 1
    processing.configure_processing(db_session)
    assert encode_pool.conversion_workers() == 3
    assert encode_pool.thumbnail_workers() == 2
    queue.set_download_workers(1)
    assert encode_pool.conversion_workers() == 3


@pytest.mark.parametrize("value", [0, -1, 65, 1.5, True, "4", None])
@pytest.mark.parametrize("field", ["conversionWorkers", "thumbnailWorkers"])
def test_worker_limits_reject_invalid_values(client: TestClient, field: str, value) -> None:
    payload = {"conversionWorkers": 2, "thumbnailWorkers": 2, field: value}
    assert client.put(URL, json=payload).status_code == 422
    assert client.get(URL).json()["conversionWorkers"] == settings.encode_workers


def test_cpu_count_fallback_and_legacy_default(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(processing.os, "process_cpu_count", lambda: None)
    monkeypatch.setattr(settings, "encode_workers", 4)
    config = client.get(URL).json()
    assert config["cpuThreads"] == 1
    assert config["conversionWorkers"] == config["thumbnailWorkers"] == 4
    assert config["recommendedConversionWorkers"] == config["recommendedThumbnailWorkers"] == 1


def test_concurrent_saves_cannot_apply_stale_worker_limits(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    first_read = threading.Event()
    release = threading.Event()
    applied = []
    real_configure = processing.configure_workers

    def apply(conversion, thumbnails):
        applied.append((conversion, thumbnails))
        if len(applied) == 1:
            first_read.set()
            assert release.wait(3)
        real_configure(conversion, thumbnails)

    monkeypatch.setattr(processing, "configure_workers", apply)
    with ThreadPoolExecutor(max_workers=2) as callers:
        first = callers.submit(
            client.put, URL, json={"conversionWorkers": 2, "thumbnailWorkers": 3}
        )
        second = None
        try:
            assert first_read.wait(3)
            second = callers.submit(
                client.put, URL, json={"conversionWorkers": 4, "thumbnailWorkers": 5}
            )
            deadline = time.monotonic() + 3
            while client.get(URL).json()["conversionWorkers"] != 4:
                assert time.monotonic() < deadline
                threading.Event().wait(0.01)
            assert not second.done(), "the second save must wait to apply its fresh budgets"
        finally:
            release.set()
        assert first.result(timeout=3).status_code == 200
        assert second is not None and second.result(timeout=3).status_code == 200
    assert applied == [(2, 3), (4, 5)]
    assert encode_pool.conversion_workers() == 4
    assert encode_pool.thumbnail_workers() == 5
