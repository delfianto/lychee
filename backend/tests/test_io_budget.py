"""Global I/O permits bound resources without bounding whole operation lifetimes."""

import io
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from contextvars import copy_context
from pathlib import Path
from time import monotonic

import httpx
import pytest
from fastapi.testclient import TestClient
from src.ingest import scanner
from src.library import service
from src.providers.mangadex_client import MangaDexClient
from src.tasks.context import (
    Operation,
    OperationCancelled,
    checkpoint,
    current_operation,
    report_phase,
)
from src.tasks.queue import io_slot, queue

from tests.test_pipeline_operations import png


def test_filesystem_and_metadata_requests_share_one_live_budget(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue.set_sync_workers(2)
    lock = threading.Lock()
    entered = []
    gates = {key: threading.Event() for key in ("scan", "metadata", "third")}
    starts = {key: threading.Event() for key in gates}
    scan_path = tmp_path / "scan.cbz"
    scan_path.write_bytes(b"archive")
    real_open = Path.open

    def block(key):
        with lock:
            entered.append(key)
            starts[key].set()
        assert gates[key].wait(5)

    @contextmanager
    def open_file(path, *args, **kwargs):
        if path == scan_path:
            block("scan")
            yield io.BytesIO(b"archive")
        else:
            with real_open(path, *args, **kwargs) as handle:
                yield handle

    monkeypatch.setattr(Path, "open", open_file)

    def request(req):
        block(req.url.path.removeprefix("/"))
        return httpx.Response(200, json={})

    api = MangaDexClient(
        client=httpx.Client(base_url="https://api", transport=httpx.MockTransport(request))
    )
    with ThreadPoolExecutor(max_workers=3) as workers:
        scan = workers.submit(scanner._signature, scan_path)
        metadata = workers.submit(api.get, "/metadata")
        try:
            assert starts["scan"].wait(3)
            assert starts["metadata"].wait(3)
            third = workers.submit(api.get, "/third")
            assert not starts["third"].wait(0.1)
            queue.set_sync_workers(1)
            gates["scan"].set()
            scan.result(timeout=3)
            assert not starts["third"].wait(0.1), "reduction must drain before admitting more I/O"
            queue.set_sync_workers(2)
            assert starts["third"].wait(3), "raising the budget must expand active work"
            assert queue.io_limit.active == 2
        finally:
            for gate in gates.values():
                gate.set()
        assert metadata.result(timeout=3).status_code == 200
        assert third.result(timeout=3).status_code == 200
    assert entered == ["scan", "metadata", "third"] or entered == ["metadata", "scan", "third"]
    assert queue.io_limit.active == 0


def test_nested_metadata_reuses_permit_but_child_threads_do_not(client: TestClient) -> None:
    started = threading.Event()
    api = MangaDexClient(
        client=httpx.Client(
            base_url="https://api", transport=httpx.MockTransport(lambda _: httpx.Response(200))
        )
    )

    def child():
        with io_slot():
            started.set()

    with ThreadPoolExecutor(max_workers=1) as worker:
        with io_slot():
            assert api.get("/nested").status_code == 200
            assert queue.io_limit.active == 1
            pending = worker.submit(copy_context().run, child)
            assert not started.wait(0.1)
        pending.result(timeout=3)
    assert started.is_set()
    assert queue.io_limit.active == 0


def test_waiting_io_cancellation_does_not_leak_a_permit(client: TestClient) -> None:
    cancel = threading.Event()
    waiting = threading.Event()

    def check():
        waiting.set()
        if cancel.is_set():
            raise OperationCancelled()

    def run():
        token = current_operation.set(Operation("waiting", check, lambda *_: None))
        try:
            with io_slot():
                raise AssertionError("cancelled work must never acquire capacity")
        finally:
            current_operation.reset(token)

    with ThreadPoolExecutor(max_workers=1) as worker, io_slot():
        pending = worker.submit(run)
        assert waiting.wait(3)
        cancel.set()
        with pytest.raises(OperationCancelled):
            pending.result(timeout=3)
        assert queue.io_limit.active == 1
    assert queue.io_limit.active == 0


@pytest.mark.parametrize("same_library", [False, True])
def test_scan_releases_io_for_another_scan_but_owns_thumbnail_cancellation(
    same_library: bool, client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    thumbnail = threading.Event()
    release = threading.Event()
    libraries = []
    for index in range(2):
        root = tmp_path / str(index)
        folder = root / "Artist" / "Set"
        folder.mkdir(parents=True)
        (folder / "1.png").write_bytes(png())
        result = client.post(
            "/api/libraries",
            json={"name": f"Library {index}", "path": str(root), "kind": "gallery"},
        )
        libraries.append(result.json()["id"])

    def covers(_session, _store, library_id):
        report_phase("covers", 0, 1)
        if not thumbnail.is_set():
            thumbnail.set()
            while not release.wait(0.02):
                checkpoint()
            checkpoint()
        report_phase("covers", 1, 1)
        return 0

    monkeypatch.setattr(service, "warm_library_covers", covers)
    monkeypatch.setattr(service, "warm_gallery_item_thumbs", lambda *_a, **_kw: 0)
    first = client.post(f"/api/libraries/{libraries[0]}/scan").json()["id"]
    try:
        assert thumbnail.wait(3)
        assert queue.io_limit.active == 0
        second_library = libraries[0] if same_library else libraries[1]
        second = client.post(f"/api/libraries/{second_library}/scan").json()["id"]
        deadline = monotonic() + 3
        tasks = {}
        while monotonic() < deadline:
            tasks = {t["id"]: t for t in client.get("/api/tasks").json()}
            if tasks[second]["status"] == "done":
                break
            threading.Event().wait(0.01)
        assert tasks[second]["status"] == "done"
        assert tasks[first]["status"] == "running"
        assert tasks[first]["phases"]["covers"] == {"completed": 0, "total": 1}
        client.post(f"/api/tasks/{first}/cancel")
        queue.wait_idle(timeout=3)
        tasks = {t["id"]: t for t in client.get("/api/tasks").json()}
        assert tasks[first]["status"] == "cancelled"
    finally:
        release.set()
        queue.wait_idle()
    assert queue.io_limit.active == 0


def test_background_thumbnail_workers_release_database_connections_before_encoding(
    client: TestClient, db_engine, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from sqlalchemy.pool import QueuePool
    from src.media import thumbnails

    started = threading.Event()
    release = threading.Event()
    root = tmp_path / "gallery"
    folder = root / "Artist" / "Set"
    folder.mkdir(parents=True)
    (folder / "1.png").write_bytes(png())
    library = client.post(
        "/api/libraries", json={"name": "No held connections", "path": str(root), "kind": "gallery"}
    ).json()["id"]
    real_encode = thumbnails.encode_thumbnail

    def encode(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return real_encode(*args, **kwargs)

    monkeypatch.setattr(thumbnails, "encode_thumbnail", encode)
    task_id = client.post(f"/api/libraries/{library}/scan").json()["id"]
    try:
        assert started.wait(3)
        assert queue.io_limit.active == 0
        assert isinstance(db_engine.pool, QueuePool)
        assert db_engine.pool.checkedout() == 0, (
            "coordinators and CPU waiters must release database reads"
        )
        assert client.get("/api/libraries").status_code == 200
        client.post(f"/api/tasks/{task_id}/cancel")
    finally:
        release.set()
        queue.wait_idle()
    task = next(t for t in client.get("/api/tasks").json() if t["id"] == task_id)
    assert task["status"] == "cancelled"


def test_scan_does_not_hold_io_permits_during_database_reconciliation(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A writer waiting for SQLite while holding the sole I/O permit could block
    # another scan's next file lookup while that scan owns the write transaction.
    real_ingest = scanner._ingest_series
    reconciled = []

    def ingest(*args, **kwargs):
        assert queue.io_limit.active == 0
        reconciled.append(kwargs["path_rel"])
        return real_ingest(*args, **kwargs)

    monkeypatch.setattr(scanner, "_ingest_series", ingest)
    monkeypatch.setattr(service, "warm_library_covers", lambda *_: 0)
    monkeypatch.setattr(service, "warm_gallery_item_thumbs", lambda *_a, **_kw: 0)
    root = tmp_path / "gallery"
    for index in range(3):
        folder = root / "Artist" / str(index)
        folder.mkdir(parents=True)
        (folder / "1.png").write_bytes(png())
    library = client.post(
        "/api/libraries", json={"name": "Reconciliation", "path": str(root), "kind": "gallery"}
    ).json()["id"]
    task_id = client.post(f"/api/libraries/{library}/scan").json()["id"]
    queue.wait_idle()
    assert len(reconciled) == 3
    task = next(t for t in client.get("/api/tasks").json() if t["id"] == task_id)
    assert task["status"] == "done"
