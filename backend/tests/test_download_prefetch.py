"""File fetching owns its children and continues independently of blocked encoders."""

import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from src.downloads.pipeline import FetchProgress, prefetch_pages
from src.downloads.provider import RemoteChapter, register_provider
from src.media import encode_pool
from src.providers.mangadex import MangaDexProvider
from src.tasks.context import Operation, OperationCancelled, current_operation
from src.tasks.queue import queue

from tests.support import ensure_manga_library, make_series
from tests.test_pipeline_operations import png


def test_progress_is_coalesced_and_only_applied_by_owner() -> None:
    owner = threading.get_ident()
    applied = []

    def apply(done, total):
        assert threading.get_ident() == owner
        progress.drain()  # reporting checkpoints must not recursively drain
        applied.append((done, total))

    progress = FetchProgress(apply)
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(lambda: [progress.post(i, 20) for i in range(21)]).result(timeout=3)
    assert applied == []
    progress.drain()
    assert applied == [(20, 20)]
    progress.post(21, 21)
    assert applied[-1] == (21, 21)


def test_source_failure_propagates_and_source_is_closed(tmp_path: Path) -> None:
    closed = threading.Event()

    def source():
        try:
            yield tmp_path / "first"
            raise RuntimeError("network failed")
        finally:
            closed.set()

    with pytest.raises(RuntimeError, match="network failed"):
        list(prefetch_pages(source(), lambda: None))
    assert closed.is_set()


def test_source_close_failure_signals_consumer_instead_of_hanging(tmp_path: Path) -> None:
    class BadClose:
        def __iter__(self):
            yield tmp_path / "one"

        def close(self):
            raise RuntimeError("close failed")

    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(lambda: list(prefetch_pages(BadClose(), lambda: None)))
        with pytest.raises(RuntimeError, match="close failed"):
            result.result(timeout=3)


def test_consumer_close_joins_fetcher_before_workspace_can_be_removed(tmp_path: Path) -> None:
    started = threading.Event()
    release = threading.Event()
    closed = threading.Event()
    iterator_ready = threading.Event()

    def source():
        try:
            yield tmp_path / "first"
            started.set()
            assert release.wait(3)
            assert tmp_path.exists()
            yield tmp_path / "second"
        finally:
            closed.set()

    def own():
        pages = prefetch_pages(source(), lambda: None)
        next(pages)
        assert started.wait(3)
        iterator_ready.set()
        pages.close()
        assert closed.is_set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        owner = pool.submit(own)
        try:
            assert iterator_ready.wait(3)
            assert not owner.done()
        finally:
            release.set()
        owner.result(timeout=3)


def test_cancelled_prefetch_removes_progress_check_and_joins(tmp_path: Path) -> None:
    cancel = threading.Event()
    closed = threading.Event()

    def check():
        if cancel.is_set():
            raise OperationCancelled()

    def source():
        try:
            yield tmp_path / "one"
            cancel.wait(3)
        finally:
            closed.set()

    operation = Operation("prefetch", check, lambda *_: None)
    token = current_operation.set(operation)
    pages = prefetch_pages(source(), lambda: None)
    try:
        next(pages)
        cancel.set()
        with pytest.raises(OperationCancelled):
            next(pages)
        assert closed.is_set()
        assert operation.checks == []
    finally:
        cancel.set()
        pages.close()
        current_operation.reset(token)


def test_ten_file_requests_continue_staging_while_conversion_is_blocked(
    client: TestClient, db_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class ThreadProcesses(ThreadPoolExecutor):
        def __init__(self, *, max_workers, mp_context):
            super().__init__(max_workers=max_workers)

    monkeypatch.setattr(encode_pool, "ProcessPoolExecutor", ThreadProcesses)
    encode_pool.configure_workers(2, 1)
    queue.set_download_workers(10)
    provider = MangaDexProvider()
    register_provider(provider)
    remote = RemoteChapter("chapter", "1", 1, None, "en")
    monkeypatch.setattr(provider, "list_chapters", lambda *_a, **_kw: [remote])
    monkeypatch.setattr(
        provider,
        "_at_home",
        lambda _: {
            "baseUrl": "https://node",
            "chapter": {"hash": "hash", "data": [str(i) for i in range(20)]},
        },
    )
    barrier = threading.Barrier(10)
    lock = threading.Lock()
    fetched = 0
    active = 0
    peak = 0
    encoding = threading.Event()
    release = threading.Event()
    all_fetched = threading.Event()
    raw = png()

    def fetch(_chapter, base, _quality, _hash, _filename):
        nonlocal fetched, active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            barrier.wait(timeout=5)
            return raw, base
        finally:
            with lock:
                active -= 1
                fetched += 1
                if fetched == 20:
                    all_fetched.set()

    def encode(*_a, **_kw):
        encoding.set()
        assert release.wait(5)
        return b"encoded"

    monkeypatch.setattr(provider, "_fetch_page", fetch)
    monkeypatch.setattr(encode_pool, "encode_bytes", encode)
    # Leave publication out of this test: cancel at the blocked conversion boundary.
    library = tmp_path / "manga"
    ensure_manga_library(db_session, library)
    series = make_series(db_session, title="Ten requests", kind="manga")
    series.provider = "mangadex"
    series.provider_series_id = "remote"
    db_session.commit()
    response = client.post("/api/downloads", json={"seriesId": series.id})
    assert response.status_code == 202
    try:
        assert encoding.wait(3)
        assert all_fetched.wait(3), "CPU work must not stall the next network batch"
        assert peak == 10
        # Fetch callbacks are marshalled to the chapter owner while it waits on CPUs.
        import time

        deadline = time.monotonic() + 3
        row = None
        while time.monotonic() < deadline:
            row = client.get("/api/downloads").json()[0]
            if row["phases"]["fetching"]["completed"] == 20:
                break
            threading.Event().wait(0.01)
        assert row is not None
        assert row["phases"]["fetching"] == {"completed": 20, "total": 20}
        assert row["phases"]["encoding"] == {"completed": 0, "total": 20}
        assert len(list((library / "temp").rglob("*.source"))) == 20
        client.post("/api/downloads", json={"action": "cancel-all"})
        assert client.get("/api/downloads").json()[0]["status"] != "done"
    finally:
        release.set()
    queue.wait_idle()
    assert client.get("/api/downloads").json()[0]["status"] == "cancelled"
    assert not list((library / "temp").iterdir())
    assert encode_pool._conversion.limiter.active == 0
