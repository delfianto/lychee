"""Verify real overlap and cancellation at boundaries between pipeline stages."""

from __future__ import annotations

import io
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session
from src.core.config import settings
from src.downloads.provider import RemoteChapter, register_provider
from src.providers.mangadex import MangaDexProvider
from src.tasks.context import checkpoint
from src.tasks.queue import queue

from tests.support import ensure_manga_library, make_series


def png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (20, 30), "white").save(output, "PNG")
    return output.getvalue()


def test_mangadex_fetches_files_concurrently_and_preserves_page_order(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue.set_download_workers(3)
    provider = MangaDexProvider()
    monkeypatch.setattr(
        provider,
        "_at_home",
        lambda _: {"baseUrl": "https://node", "chapter": {"hash": "hash", "data": ["1", "2", "3"]}},
    )
    barrier = threading.Barrier(3)

    def fetch(_chapter, base, _quality, _hash, filename):
        barrier.wait(timeout=3)
        return filename.encode(), base

    monkeypatch.setattr(provider, "_fetch_page", fetch)
    progress = []
    paths = provider.fetch_pages_to(
        RemoteChapter("id", "1", 1, None, "en"),
        tmp_path,
        on_page=lambda done, total: progress.append((done, total)),
    )
    assert [path.read_bytes() for path in paths] == [b"1", b"2", b"3"]
    assert progress == [(0, 3), (1, 3), (2, 3), (3, 3)]


@pytest.mark.parametrize("action", ["cancel-all", "delete"])
def test_download_converts_before_fetch_finishes_and_owns_thumbnail_cancellation(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
) -> None:
    from src.downloads import downloader

    converted = threading.Event()
    thumbnail_started = threading.Event()
    release = threading.Event()
    real_encode = downloader.encode_pages

    class StreamingProvider:
        id = "streaming-test"

        def list_chapters(self, provider_series_id: str, *, language: str = "en"):
            return [RemoteChapter("id", "1", 1, None, language)]

        def fetch_pages(
            self, chapter: RemoteChapter, *, data_saver: bool = False, on_page=None
        ) -> list[bytes]:
            raise AssertionError("streaming path must be used")

        def iter_pages_to(self, _chapter, directory, *, data_saver=False, on_page=None):
            assert on_page is not None
            on_page(0, 2)
            for index in range(1, 3):
                if index == 2:
                    assert converted.wait(3), "conversion must overlap file fetching"
                path = directory / f"{index}.source"
                path.write_bytes(png())
                on_page(index, 2)
                yield path

    def encode(raws):
        for result in real_encode(raws):
            converted.set()
            yield result

    def cover(*_args):
        thumbnail_started.set()
        assert release.wait(3)
        checkpoint()
        return True

    monkeypatch.setattr(downloader, "encode_pages", encode)
    monkeypatch.setattr(downloader, "write_series_cover", cover)
    register_provider(StreamingProvider())
    ensure_manga_library(db_session, tmp_path / "manga")
    series = make_series(db_session, title="Pipeline", kind="manga")
    series.provider = "streaming-test"
    series.provider_series_id = "remote"
    db_session.commit()
    response = client.post("/api/downloads", json={"seriesId": series.id})
    assert thumbnail_started.wait(3)
    try:
        row = client.get("/api/downloads").json()[0]
        assert row["status"] == "downloading"
        assert row["phase"] == "thumbnails"
        assert row["progress"] < 100
        assert row["phases"]["fetching"] == {"completed": 2, "total": 2}
        assert row["phases"]["encoding"] == {"completed": 2, "total": 2}
        if action == "cancel-all":
            client.post("/api/downloads", json={"action": "cancel-all"})
        else:
            assert client.delete(f"/api/downloads/{row['id']}").status_code == 204
    finally:
        release.set()
    queue.wait_idle()
    remaining = client.get("/api/downloads").json()
    if action == "cancel-all":
        assert remaining[0]["status"] == "cancelled"
    else:
        assert remaining == []
    task = next(t for t in client.get("/api/tasks").json() if t["id"] == response.json()["id"])
    assert task["status"] == "cancelled"
    assert not list((tmp_path / "manga" / "temp").iterdir())


def _gallery(client: TestClient, tmp_path: Path) -> str:
    for index in range(3):
        folder = tmp_path / "gallery" / "Artist" / f"Set {index}"
        folder.mkdir(parents=True)
        (folder / "1.png").write_bytes(png())
    response = client.post(
        "/api/libraries",
        json={"name": "Gallery pipeline", "path": str(tmp_path / "gallery"), "kind": "gallery"},
    )
    return response.json()["id"]


@pytest.mark.parametrize("control", ["sync", "activity-while-paused"])
def test_gallery_thumbnails_are_parallel_and_cancel_with_scan(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, control: str
) -> None:
    from src.catalog import media
    from src.library import service

    monkeypatch.setattr(settings, "encode_workers", 2)
    monkeypatch.setattr(service, "warm_library_covers", lambda *_: 0)
    barrier = threading.Barrier(2)
    started = threading.Event()
    release = threading.Event()

    def thumbnail(*_args):
        barrier.wait(timeout=3)
        started.set()
        assert release.wait(3)
        checkpoint()
        return True

    monkeypatch.setattr(media, "ensure_gallery_item_thumb", thumbnail)
    library_id = _gallery(client, tmp_path)
    response = client.post(f"/api/libraries/{library_id}/scan")
    assert started.wait(3), "gallery items must encode concurrently"
    try:
        task = next(t for t in client.get("/api/tasks").json() if t["id"] == response.json()["id"])
        assert task["status"] == "running"
        assert task["phases"]["thumbnails"] == {"completed": 0, "total": 3}
        job = next(
            j for j in client.get("/api/sync").json()["jobs"] if j["title"] == "Gallery pipeline"
        )
        assert job["status"] == "running"
        if control == "sync":
            client.post("/api/sync/control", json={"action": "cancel", "jobId": job["id"]})
        else:
            client.post("/api/sync/control", json={"action": "pause", "jobId": job["id"]})
            client.post(f"/api/tasks/{response.json()['id']}/cancel")
        task = next(t for t in client.get("/api/tasks").json() if t["id"] == response.json()["id"])
        assert task["status"] == "cancelling"
    finally:
        release.set()
    queue.wait_idle()
    task = next(t for t in client.get("/api/tasks").json() if t["id"] == response.json()["id"])
    assert task["status"] == "cancelled"
    job = next(
        j for j in client.get("/api/sync").json()["jobs"] if j["title"] == "Gallery pipeline"
    )
    assert job["status"] == "cancelled"


def test_cancel_during_parallel_scan_inspection_never_starts_thumbnail_work(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.ingest import scanner
    from src.library import service

    queue.set_sync_workers(2)
    barrier = threading.Barrier(2)
    started = threading.Event()
    release = threading.Event()
    real_signature = scanner._signature
    warmed = []

    def signature(path):
        barrier.wait(timeout=3)
        started.set()
        assert release.wait(3)
        checkpoint()
        return real_signature(path)

    monkeypatch.setattr(scanner, "_signature", signature)
    monkeypatch.setattr(service, "warm_library_covers", lambda *_: warmed.append(True))
    library_id = _gallery(client, tmp_path)
    response = client.post(f"/api/libraries/{library_id}/scan")
    assert started.wait(3), "filesystem inspection must overlap"
    try:
        assert client.post(f"/api/tasks/{response.json()['id']}/cancel").status_code == 200
    finally:
        release.set()
    queue.wait_idle()
    task = next(t for t in client.get("/api/tasks").json() if t["id"] == response.json()["id"])
    assert task["status"] == "cancelled"
    assert warmed == []
    assert client.post("/api/tasks/missing/cancel").status_code == 404


def test_video_cancellation_kills_and_reaps_the_poster_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.media import video
    from src.tasks.context import OperationCancelled

    events = []

    class Process:
        def __init__(self, *_args, **_kwargs):
            events.append("started")

        def kill(self):
            events.append("killed")

        def communicate(self, **_kwargs):
            events.append("reaped")
            return b"", b""

    def cancelled():
        raise OperationCancelled("Cancelled")

    monkeypatch.setattr(video, "_FFMPEG", "ffmpeg")
    monkeypatch.setattr(video.subprocess, "Popen", Process)
    monkeypatch.setattr(video, "checkpoint", cancelled)
    with pytest.raises(OperationCancelled):
        video.extract_poster_png(tmp_path / "video.mp4")
    assert events == ["started", "killed", "reaped"]


def test_live_limit_reduction_waits_for_running_work_before_admitting_more() -> None:
    from concurrent.futures import ThreadPoolExecutor

    from src.tasks.concurrency import Limiter

    limiter = Limiter(2)
    barrier = threading.Barrier(3)
    release_first = threading.Event()
    release_second = threading.Event()
    third_started = threading.Event()

    def running(release):
        with limiter.slot():
            barrier.wait(timeout=3)
            assert release.wait(3)

    def third():
        with limiter.slot():
            third_started.set()

    with ThreadPoolExecutor(max_workers=3) as pool:
        first = pool.submit(running, release_first)
        second = pool.submit(running, release_second)
        barrier.wait(timeout=3)
        try:
            limiter.resize(1)
            pending = pool.submit(third)
            assert not third_started.wait(0.05)
            release_first.set()
            first.result(timeout=3)
            assert not third_started.wait(0.05)
        finally:
            release_first.set()
            release_second.set()
        second.result(timeout=3)
        pending.result(timeout=3)
        assert third_started.is_set()


def test_rate_limit_and_retry_waits_stop_promptly_on_operation_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from types import SimpleNamespace

    from src.tasks import context

    now = [0.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    def cancel_after_two_ticks():
        if now[0] >= 0.2:
            raise context.OperationCancelled("Cancelled")

    monkeypatch.setattr(context, "time", SimpleNamespace(monotonic=lambda: now[0], sleep=sleep))
    token = context.current_operation.set(
        context.Operation(
            "test",
            cancel_after_two_ticks,
            lambda *_: None,
        )
    )
    try:
        with pytest.raises(context.OperationCancelled):
            context.cooperative_wait(60)
    finally:
        context.current_operation.reset(token)
    assert sleeps == [0.1, 0.1]


def test_active_mangadex_fetch_grows_from_one_to_five_before_first_file_finishes(
    client: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from concurrent.futures import ThreadPoolExecutor

    provider = MangaDexProvider()
    monkeypatch.setattr(
        provider,
        "_at_home",
        lambda _: {
            "baseUrl": "https://node",
            "chapter": {"hash": "hash", "data": list("12345")},
        },
    )
    first_started = threading.Event()
    five_started = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    started = []

    def fetch(_chapter, base, _quality, _hash, filename):
        with lock:
            started.append(filename)
            first_started.set()
            if len(started) == 5:
                five_started.set()
        assert release.wait(5)
        return filename.encode(), base

    monkeypatch.setattr(provider, "_fetch_page", fetch)
    with ThreadPoolExecutor(max_workers=1) as consumer:
        result = consumer.submit(
            provider.fetch_pages_to, RemoteChapter("id", "1", 1, None, "en"), tmp_path
        )
        try:
            assert first_started.wait(3)
            assert started == ["1"]
            assert (
                client.patch("/api/downloads/config", json={"parallelDownloads": 5}).status_code
                == 200
            )
            assert five_started.wait(3), (
                "new file requests must start before the first request returns"
            )
        finally:
            release.set()
        assert [path.read_bytes() for path in result.result(timeout=3)] == [
            b"1",
            b"2",
            b"3",
            b"4",
            b"5",
        ]


def test_next_chapter_fetches_while_previous_chapter_is_encoding(
    client: TestClient, db_session: Session, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from src.downloads import downloader

    fetched = threading.Event()
    encoding = threading.Event()
    release = threading.Event()
    lock = threading.Lock()
    fetches = []
    real_encode = downloader.encode_pages

    class PipelineProvider:
        id = "chapter-handoff"

        def list_chapters(self, provider_series_id, *, language="en"):
            return [RemoteChapter(str(i), str(i), 1, None, language) for i in (1, 2)]

        def fetch_pages(self, chapter, *, data_saver=False, on_page=None):
            with lock:
                fetches.append(chapter.number)
                if len(fetches) == 2:
                    fetched.set()
            return [png()]

    def encode(raws):
        for raw in raws:
            encoding.set()
            assert release.wait(5)
            yield from real_encode([raw])

    monkeypatch.setattr(downloader, "encode_pages", encode)
    register_provider(PipelineProvider())
    ensure_manga_library(db_session, tmp_path / "manga")
    series = make_series(db_session, title="Chapter handoff", kind="manga")
    series.provider = PipelineProvider.id
    db_session.commit()
    response = client.post("/api/downloads", json={"seriesId": series.id})
    try:
        assert encoding.wait(3)
        assert fetched.wait(3), "encoding must not hold the next chapter's fetching slot"
        from time import monotonic

        deadline = monotonic() + 3
        while queue.fetch_limit.active and monotonic() < deadline:
            threading.Event().wait(0.01)
        assert queue.fetch_limit.active == 0
        task = next(t for t in client.get("/api/tasks").json() if t["id"] == response.json()["id"])
        assert task["status"] == "running"
        assert not any(row["status"] == "done" for row in client.get("/api/downloads").json())
        # File-request tuning no longer controls whole chapter lifetimes.
        assert queue.download_workers == 1
        assert sorted(fetches) == ["1", "2"]
    finally:
        release.set()
    queue.wait_idle()
    assert all(row["status"] == "done" for row in client.get("/api/downloads").json())
