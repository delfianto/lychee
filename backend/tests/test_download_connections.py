"""Several series must not retain connections while waiting for chapter capacity."""

import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import QueuePool
from src.catalog.models import Chapter
from src.core.persistence.database import create_database_engine, get_db
from src.downloads import downloader, service
from src.downloads.models import DownloadTask
from src.downloads.provider import RemoteChapter, register_provider
from src.main import app
from src.tasks.queue import queue

from tests.support import ensure_manga_library, make_series
from tests.test_pipeline_operations import png


class SmallProvider:
    id = "connection-test"

    def list_chapters(self, provider_series_id: str, *, language="en"):
        return [RemoteChapter(str(i), str(i), 1, None, language) for i in (1, 2)]

    def fetch_pages(self, chapter: RemoteChapter, *, data_saver=False, on_page=None):
        return [png() for _ in range(20)]


def test_waiting_series_release_all_connections_before_admission(
    client: TestClient,
    db_session: Session,
    db_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    register_provider(SmallProvider())
    ensure_manga_library(db_session, tmp_path / "manga")
    ids = []
    for index in range(3):
        series = make_series(db_session, title=f"Waiting {index}")
        series.provider = SmallProvider.id
        db_session.flush()
        ids.append(series.id)
        db_session.add(
            DownloadTask(
                series_id=series.id,
                chapter_label="Ch. 1",
                provider=SmallProvider.id,
                remote_json=asdict(RemoteChapter("1", "1", 1, None, "en")),
            )
        )
    db_session.commit()
    # The same tiny pool is used by both API and download workers.
    small = create_database_engine(
        str(db_engine.url),
        pool_size=2,
        max_overflow=0,
        pool_timeout=0.2,
    )
    factory = sessionmaker(bind=small, expire_on_commit=False)

    def database():
        with factory() as session:
            yield session

    app.dependency_overrides[get_db] = database
    queue.chapter_limit.resize(1)
    real_slot = queue.chapter_limit.slot
    held = real_slot()
    held.__enter__()
    reached = threading.Barrier(4)
    calls = 0
    lock = threading.Lock()

    @contextmanager
    def slot():
        nonlocal calls
        with lock:
            calls += 1
            first = calls <= 3
        if first:
            reached.wait(timeout=3)
        with real_slot():
            yield

    monkeypatch.setattr(queue.chapter_limit, "slot", slot)

    def drain(sid):
        with factory() as session:
            return service._drain_parallel(session, sid, tmp_path / "storage", lambda *_a: None)

    try:
        with ThreadPoolExecutor(max_workers=3) as callers:
            pending = [callers.submit(drain, sid) for sid in ids]
            try:
                reached.wait(timeout=3)
                assert isinstance(small.pool, QueuePool)
                assert small.pool.checkedout() == 0
                assert client.get("/api/series").status_code == 200
                assert client.get("/api/downloads").status_code == 200
            finally:
                held.__exit__(None, None, None)
            assert [job.result(timeout=5) for job in pending] == [1, 1, 1]
    finally:
        queue.chapter_limit.resize(10)
        small.dispose()


def test_failed_flush_rolls_back_and_does_not_orphan_the_chapter(
    client: TestClient, db_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    register_provider(SmallProvider())
    ensure_manga_library(db_session, tmp_path / "manga")
    series = make_series(db_session, title="Invalid transaction")
    series.provider = SmallProvider.id
    db_session.commit()
    series_id = series.id
    real_download = downloader._download_chapter

    def download(session, **kwargs):
        if kwargs["remote"].number == "1":
            session.add(Chapter(series_id=series_id))  # missing required book_id
            session.flush()
        return real_download(session, **kwargs)

    monkeypatch.setattr(downloader, "_download_chapter", download)
    assert client.post("/api/downloads", json={"seriesId": series.id}).status_code == 202
    queue.wait_idle()
    assert sorted(row["status"] for row in client.get("/api/downloads").json()) == [
        "done",
        "failed",
    ]


def test_page_updates_coalesce_sql_but_flush_final_counters(
    client: TestClient,
    db_session: Session,
    db_engine: Engine,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = SmallProvider()
    monkeypatch.setattr(
        provider, "list_chapters", lambda *_a, **_kw: [RemoteChapter("1", "1", 1, None, "en")]
    )
    register_provider(provider)
    ensure_manga_library(db_session, tmp_path / "manga")
    series = make_series(db_session, title="Coalesced")
    series.provider = provider.id
    db_session.commit()
    monkeypatch.setattr(downloader, "monotonic", lambda: 1.0)
    updates = []

    def statement(_conn, _cursor, sql, *_args):
        if sql.lower().startswith("update download_task"):
            updates.append(sql)

    event.listen(db_engine, "before_cursor_execute", statement)
    try:
        client.post("/api/downloads", json={"seriesId": series.id})
        queue.wait_idle()
    finally:
        event.remove(db_engine, "before_cursor_execute", statement)
    row = client.get("/api/downloads").json()[0]
    assert row["status"] == "done"
    assert row["phases"]["encoding"] == {"completed": 20, "total": 20}
    assert row["phases"]["fetching"] == {"completed": 20, "total": 20}
    assert len(updates) < 10
