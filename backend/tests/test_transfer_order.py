"""Chapter admission and visible work order must not depend on random IDs."""

import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from src.downloads.downloader import plan_downloads
from src.downloads.models import DownloadTask
from src.downloads.provider import RemoteChapter, register_provider
from src.integrations.sync import SyncJobManager
from src.tasks.concurrency import Limiter
from src.tasks.context import Operation, OperationCancelled, current_operation
from src.tasks.ordering import chapter_key, natural_key
from src.tasks.queue import queue

from tests.support import ensure_manga_library, make_series
from tests.test_pipeline_operations import png


def test_download_claims_lowest_chapter_with_tied_times_and_shuffled_ids(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    fetched = []
    numbers = ["10", "9.5", "9.10", "2.1", "2.02", "2", "1", "0", "-1", "Oneshot"]

    class Provider:
        id = "order-test"

        def list_chapters(self, *args, **kwargs):
            return [RemoteChapter(f"pid-{number}", number, None, None, "en") for number in numbers]

        def fetch_pages(self, chapter, **kwargs):
            fetched.append(chapter.number)
            return [png()]

    provider = Provider()
    register_provider(provider)
    ensure_manga_library(db_session, tmp_path / "manga")
    series = make_series(db_session, title="Ordered")
    series.provider, series.provider_series_id = provider.id, "remote"
    db_session.flush()
    for index, remote in enumerate(provider.list_chapters()):
        db_session.add(
            DownloadTask(
                id=f"{index:012d}",
                series_id=series.id,
                chapter_label=f"Ch. {remote.number}",
                provider=provider.id,
                remote_json=asdict(remote),
                created_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        )
    db_session.commit()
    assert client.post("/api/downloads", json={"seriesId": series.id}).status_code == 202
    queue.wait_idle()
    assert fetched == ["-1", "0", "1", "2", "2.02", "2.1", "9.10", "9.5", "10", "Oneshot"]
    rows = client.get("/api/downloads").json()
    assert len(rows) == len(numbers) and all(row["status"] == "done" for row in rows)
    assert [row["chapter"].removeprefix("Ch. ") for row in rows] == fetched


def test_planning_limit_selects_lowest_chapters_from_an_unsorted_provider(
    db_session: Session,
) -> None:
    class Provider:
        id = "plan-order"

        def list_chapters(self, *args, **kwargs):
            return [
                RemoteChapter(number, number, None, None, "en") for number in ("10", "9.5", "2")
            ]

        def fetch_pages(self, *args, **kwargs):
            return []

    series = make_series(db_session, title="Limited")
    series.provider = Provider.id
    db_session.commit()
    assert plan_downloads(db_session, series, Provider(), limit=2) == 2
    assert {row.chapter_label for row in db_session.scalars(select(DownloadTask))} == {
        "Ch. 2",
        "Ch. 9.5",
    }


def test_download_list_pins_active_work_then_sorts_titles_and_chapters(
    client: TestClient, db_session: Session
) -> None:
    alpha = make_series(db_session, title="Alpha")
    zeta = make_series(db_session, title="Zeta")
    rows = [
        ("done", alpha, "0", "done"),
        ("queue10", alpha, "10", "queued"),
        ("queue2", alpha, "2", "queued"),
        ("active-z", zeta, "1", "downloading"),
        ("active10", alpha, "10", "downloading"),
        ("active2", alpha, "2", "downloading"),
        ("paused", alpha, "0", "paused"),
        ("failed", alpha, "0", "failed"),
    ]
    for key, series, number, status in rows:
        db_session.add(
            DownloadTask(id=key, series_id=series.id, chapter_label=f"Ch. {number}", status=status)
        )
    db_session.commit()
    assert [row["id"] for row in client.get("/api/downloads").json()] == [
        "active2",
        "active10",
        "active-z",
        "queue2",
        "queue10",
        "paused",
        "failed",
        "done",
    ]


def test_sync_plans_in_natural_title_order(client: TestClient, db_session: Session) -> None:
    starts = []

    class Provider:
        id = "sync-order"

        def list_chapters(self, provider_series_id, **kwargs):
            starts.append(provider_series_id)
            return []

        def fetch_pages(self, *args, **kwargs):
            return []

    register_provider(Provider())
    for title in ("Work 10", "Work 2", "Alpha"):
        series = make_series(db_session, title=title)
        series.provider, series.provider_series_id = Provider.id, title
    db_session.commit()
    queue.set_sync_workers(1)
    assert client.post("/api/sync").status_code == 202
    queue.wait_idle()
    assert starts == ["Alpha", "Work 2", "Work 10"]


def test_sync_job_log_is_active_first_and_natural_with_stable_equal_titles() -> None:
    jobs = SyncJobManager()
    definitions = [
        ("Zeta", "done"),
        ("Set 10", "queued"),
        ("Set 2", "queued"),
        ("Zeta", "running"),
        ("Alpha", "running"),
        ("Alpha", "paused"),
    ]
    for title, status in definitions:
        jobs.create(kind="sync", title=title, source="MangaDex", status=status)
    assert [(job.title, job.status) for job in jobs.list_jobs()] == [
        ("Alpha", "running"),
        ("Zeta", "running"),
        ("Set 2", "queued"),
        ("Set 10", "queued"),
        ("Alpha", "paused"),
        ("Zeta", "done"),
    ]
    first = jobs.create(kind="scan", title="Same", source="/disk", status="running")
    second = jobs.create(kind="scan", title="Same", source="/disk", status="running")
    assert [job.id for job in jobs.list_jobs() if job.title == "Same"] == [first.id, second.id]


def test_natural_labels_handle_decimals_and_specials() -> None:
    assert sorted(["Set 10", "Set 2", "set 1"], key=natural_key) == ["set 1", "Set 2", "Set 10"]
    assert sorted(["Ch. Oneshot", "Ch. 2.1", "Chapter 2.02", "Ch. -1"], key=chapter_key) == [
        "Ch. -1",
        "Chapter 2.02",
        "Ch. 2.1",
        "Ch. Oneshot",
    ]


def test_gallery_inspection_starts_with_lowest_natural_folder_name(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.catalog import media
    from src.catalog.models import Series
    from src.ingest import scanner

    root = tmp_path / "gallery"
    for name in ("Set 10", "Set 2", "Set 1"):
        folder = root / "Artist" / name
        folder.mkdir(parents=True)
        (folder / "1.png").write_bytes(png())
    real_signature = scanner._signature
    starts = []
    cover_starts, thumbnail_starts = [], []

    def signature(path):
        starts.append(path.name)
        return real_signature(path)

    monkeypatch.setattr(scanner, "_signature", signature)

    def cover(session, _store, series_id):
        series = session.get(Series, series_id)
        assert series is not None
        cover_starts.append(series.title)
        return True

    def thumbnail(session, _store, series_id, _index):
        series = session.get(Series, series_id)
        assert series is not None
        thumbnail_starts.append(series.title)
        return True

    monkeypatch.setattr(media, "materialize_series_cover", cover)
    monkeypatch.setattr(media, "ensure_gallery_item_thumb", thumbnail)
    created = client.post(
        "/api/libraries", json={"name": "Gallery", "path": str(root), "kind": "gallery"}
    )
    assert client.post(f"/api/libraries/{created.json()['id']}/scan").status_code == 202
    queue.wait_idle()
    assert starts == ["Set 1", "Set 2", "Set 10"]
    expected = ["Artist — Set 1", "Artist — Set 2", "Artist — Set 10"]
    assert cover_starts == thumbnail_starts == expected


def test_fifo_admission_does_not_allow_a_reacquiring_worker_to_jump_waiters() -> None:
    limiter = Limiter(1, fifo=True)
    waiting = [threading.Event() for _ in range(3)]
    order = []

    def worker(index):
        token = current_operation.set(Operation(str(index), waiting[index].set, lambda *_: None))
        try:
            with limiter.slot():
                order.append(index)
            if index == 0:
                with limiter.slot():
                    order.append(3)
        finally:
            current_operation.reset(token)

    with ThreadPoolExecutor(max_workers=3) as pool:
        with limiter.slot():
            pending = []
            for index in range(3):
                pending.append(pool.submit(worker, index))
                assert waiting[index].wait(3)
        for future in pending:
            future.result(timeout=5)
    assert order == [0, 1, 2, 3]
    assert limiter.active == 0


def test_cancelled_fifo_waiter_does_not_block_following_work() -> None:
    limiter = Limiter(1, fifo=True)
    waiting, cancel, following_waiting = threading.Event(), threading.Event(), threading.Event()
    entered = []

    def check():
        waiting.set()
        if cancel.is_set():
            raise OperationCancelled()

    def worker(cancelled):
        token = current_operation.set(
            Operation("waiter", check if cancelled else following_waiting.set, lambda *_: None)
        )
        try:
            with limiter.slot():
                entered.append("following")
        finally:
            current_operation.reset(token)

    with ThreadPoolExecutor(max_workers=2) as pool:
        with limiter.slot():
            first = pool.submit(worker, True)
            assert waiting.wait(3)
            second = pool.submit(worker, False)
            assert following_waiting.wait(3)
            cancel.set()
            with pytest.raises(OperationCancelled):
                first.result(timeout=3)
        second.result(timeout=3)
    assert entered == ["following"] and limiter.active == 0
