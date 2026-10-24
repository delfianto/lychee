"""Deterministic overlap tests use threads in place of processes, preserving real futures/limits."""

import threading
from concurrent.futures import ThreadPoolExecutor

import pytest
from PIL import UnidentifiedImageError
from src.media import encode_pool
from src.media.avif import ContentClass
from src.tasks.context import Operation, OperationCancelled, current_operation


@pytest.fixture
def threaded_workers(monkeypatch: pytest.MonkeyPatch):
    class ThreadProcesses(ThreadPoolExecutor):
        def __init__(self, *, max_workers, mp_context):
            super().__init__(max_workers=max_workers)

    monkeypatch.setattr(encode_pool, "ProcessPoolExecutor", ThreadProcesses)


def test_conversion_and_thumbnail_budgets_overlap_without_sharing_slots(
    threaded_workers, monkeypatch: pytest.MonkeyPatch
) -> None:
    encode_pool.configure_workers(2, 3)
    lock = threading.Lock()
    active = [0, 0]
    peaks = [0, 0]
    conversion_ready = threading.Event()
    thumbnails_ready = threading.Event()
    release = threading.Event()

    def job(stage: int) -> bytes:
        with lock:
            active[stage] += 1
            peaks[stage] = max(peaks[stage], active[stage])
            if active[0] == 2:
                conversion_ready.set()
            if active[1] == 3:
                thumbnails_ready.set()
        try:
            assert release.wait(3)
            return b"done"
        finally:
            with lock:
                active[stage] -= 1

    monkeypatch.setattr(encode_pool, "encode_bytes", lambda *_a, **_kw: job(0))
    monkeypatch.setattr(encode_pool, "_thumbnail", lambda *_a: job(1))
    with ThreadPoolExecutor(max_workers=8) as callers:
        futures = [
            callers.submit(lambda: list(encode_pool.encode_pages([b"page"]))) for _ in range(4)
        ]
        futures += [
            callers.submit(encode_pool.encode_thumbnail, b"image", 640, ContentClass.PHOTO, 75)
            for _ in range(4)
        ]
        try:
            assert conversion_ready.wait(3)
            assert thumbnails_ready.wait(3)
            assert active == [2, 3]
        finally:
            release.set()
        for future in futures:
            future.result(timeout=3)
    assert peaks == [2, 3]
    assert encode_pool._conversion.limiter.active == encode_pool._thumbnails.limiter.active == 0


def test_live_resize_expands_an_active_chapter_and_drains_before_lower_limit(
    threaded_workers, monkeypatch: pytest.MonkeyPatch
) -> None:
    encode_pool.configure_workers(2, 1)
    started = [threading.Event() for _ in range(7)]
    release = [threading.Event() for _ in range(7)]
    lock = threading.Lock()
    active = 0
    late_peak = 0
    lowered = False

    def job(raw: bytes, **_kw) -> bytes:
        nonlocal active, late_peak
        index = int(raw)
        with lock:
            active += 1
            if lowered:
                late_peak = max(late_peak, active)
        started[index].set()
        try:
            assert release[index].wait(5)
            return raw
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(encode_pool, "encode_bytes", job)
    with ThreadPoolExecutor(max_workers=2) as callers:
        chapter = callers.submit(
            lambda: list(encode_pool.encode_pages([str(i).encode() for i in range(6)]))
        )
        extra = None
        try:
            assert started[0].wait(3) and started[1].wait(3)
            encode_pool.configure_workers(4, 1)
            release[0].set()
            assert all(started[i].wait(3) for i in (2, 3, 4))
            assert active == 4
            encode_pool.configure_workers(1, 1)
            lowered = True
            extra = callers.submit(lambda: list(encode_pool.encode_pages([b"6"])))
            assert not started[6].wait(0.15)
            for index in (1, 2, 3):
                release[index].set()
            assert not started[6].wait(0.15)
            release[4].set()
            for event in release:
                event.set()
            assert chapter.result(timeout=3) == [str(i).encode() for i in range(6)]
            assert extra.result(timeout=3) == [b"6"]
        finally:
            for event in release:
                event.set()
    assert late_peak == 1


def test_cancelled_owner_joins_running_encodes_and_releases_all_slots(
    threaded_workers, monkeypatch: pytest.MonkeyPatch
) -> None:
    encode_pool.configure_workers(2, 1)
    gate = threading.Barrier(3)
    release = threading.Event()
    cancel = threading.Event()

    def job(*_a, **_kw):
        gate.wait(timeout=3)
        assert release.wait(3)
        return b"encoded"

    def check():
        if cancel.is_set():
            raise OperationCancelled()

    def own():
        token = current_operation.set(Operation("cpu-test", check, lambda *_a: None))
        try:
            return list(encode_pool.encode_pages([b"one", b"two", b"three"]))
        finally:
            current_operation.reset(token)

    monkeypatch.setattr(encode_pool, "encode_bytes", job)
    with ThreadPoolExecutor(max_workers=1) as caller:
        future = caller.submit(own)
        gate.wait(timeout=3)
        cancel.set()
        assert not future.done()
        release.set()
        with pytest.raises(OperationCancelled):
            future.result(timeout=3)
    assert encode_pool._conversion.limiter.active == 0


def test_submission_and_serial_failures_do_not_leak_capacity(
    threaded_workers, monkeypatch: pytest.MonkeyPatch
) -> None:
    encode_pool.configure_workers(2, 1)
    pool = encode_pool._get_pool()
    assert pool is not None
    with monkeypatch.context() as patch:
        patch.setattr(
            pool, "submit", lambda *_a, **_kw: (_ for _ in ()).throw(RuntimeError("broken pool"))
        )
        with pytest.raises(RuntimeError, match="broken pool"):
            list(encode_pool.encode_pages([b"bad"]))
    assert encode_pool._conversion.limiter.active == 0
    encode_pool.configure_workers(1, 1)
    with pytest.raises(UnidentifiedImageError):
        list(encode_pool.encode_pages([b"bad-image"]))
    assert encode_pool._conversion.limiter.active == 0


def test_worker_timeout_is_propagated_instead_of_polled_forever(
    threaded_workers, monkeypatch: pytest.MonkeyPatch
) -> None:
    encode_pool.configure_workers(2, 2)

    def timeout(*_a, **_kw):
        raise TimeoutError("codec timed out")

    monkeypatch.setattr(encode_pool, "encode_bytes", timeout)
    monkeypatch.setattr(encode_pool, "_thumbnail", timeout)
    with pytest.raises(TimeoutError, match="codec timed out"):
        list(encode_pool.encode_pages([b"page"]))
    with pytest.raises(TimeoutError, match="codec timed out"):
        encode_pool.encode_thumbnail(b"image", 640, ContentClass.PHOTO, 75)
    assert encode_pool._conversion.limiter.active == encode_pool._thumbnails.limiter.active == 0


def test_thumbnail_cancellation_joins_native_job_before_returning(
    threaded_workers, monkeypatch: pytest.MonkeyPatch
) -> None:
    encode_pool.configure_workers(1, 2)
    started = threading.Event()
    release = threading.Event()
    cancel = threading.Event()
    cancellation_seen = threading.Event()

    def thumbnail(*_a):
        started.set()
        assert release.wait(3)
        return b"thumb"

    def check():
        if cancel.is_set():
            cancellation_seen.set()
            raise OperationCancelled()

    def own():
        token = current_operation.set(Operation("thumbnail-test", check, lambda *_a: None))
        try:
            return encode_pool.encode_thumbnail(b"image", 640, ContentClass.PHOTO, 75)
        finally:
            current_operation.reset(token)

    monkeypatch.setattr(encode_pool, "_thumbnail", thumbnail)
    with ThreadPoolExecutor(max_workers=1) as callers:
        result = callers.submit(own)
        try:
            assert started.wait(3)
            cancel.set()
            assert cancellation_seen.wait(3)
            assert not result.done(), "owner must wait for the native encoder to stop"
        finally:
            release.set()
        with pytest.raises(OperationCancelled):
            result.result(timeout=3)
    assert encode_pool._thumbnails.limiter.active == 0
