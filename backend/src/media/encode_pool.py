"""Independent, live-bounded conversion and thumbnail workers.

Each AVIF job uses one native thread. Old executors drain under the same limiter
when resized, so their jobs cannot escape the new global admission budget.
"""

from __future__ import annotations

import atexit
import multiprocessing as mp
from collections.abc import Callable, Generator, Iterable
from concurrent.futures import Future, ProcessPoolExecutor, TimeoutError
from contextlib import suppress
from functools import partial
from threading import Lock
from typing import Literal

from PIL import Image, ImageOps

from src.core.config import settings
from src.media.avif import ContentClass, encode, encode_bytes, load_image
from src.tasks.concurrency import Limiter
from src.tasks.context import checkpoint

MAX_IMAGE_WORKERS = 64


class _Workers:
    def __init__(self) -> None:
        self._configured: int | None = None
        self._pool: ProcessPoolExecutor | None = None
        self._pool_size = 0
        self._retired: list[ProcessPoolExecutor] = []
        self._lock = Lock()
        self._limit = Limiter(1)

    def _count(self) -> int:
        return max(
            1,
            min(
                MAX_IMAGE_WORKERS,
                self._configured if self._configured is not None else settings.encode_workers,
            ),
        )

    def _sync_locked(self) -> int:
        count = self._count()
        if self._limit.count != count:
            self._limit.resize(count)
        if self._pool is not None and self._pool_size != count:
            # Keep running futures owned by their callers. The shared limiter
            # counts them until they finish, including across executor changes.
            self._pool.shutdown(wait=False, cancel_futures=False)
            self._retired.append(self._pool)
            self._pool = None
        return count

    def configure(self, count: int | None) -> None:
        with self._lock:
            self._configured = count
            self._sync_locked()

    @property
    def count(self) -> int:
        with self._lock:
            return self._sync_locked()

    @property
    def limiter(self) -> Limiter:
        _ = self.count
        return self._limit

    def _pool_locked(self) -> ProcessPoolExecutor | None:
        count = self._sync_locked()
        if count == 1:
            return None
        if self._pool is None:
            self._pool = ProcessPoolExecutor(max_workers=count, mp_context=mp.get_context("spawn"))
            self._pool_size = count
        return self._pool

    def pool(self) -> ProcessPoolExecutor | None:
        with self._lock:
            return self._pool_locked()

    def submit(self, job: Callable[[], bytes]) -> Future[bytes]:
        slot = self.limiter.slot()
        slot.__enter__()
        try:
            with self._lock:
                pool = self._pool_locked()
                # Submit while locked so resize cannot retire this executor
                # between choosing it and submitting its next job.
                future = pool.submit(job) if pool is not None else None
            if future is None:
                result = job()
                future = Future()
                future.set_result(result)
        except BaseException:
            slot.__exit__(None, None, None)
            raise
        future.add_done_callback(lambda _: slot.__exit__(None, None, None))
        return future

    def shutdown(self) -> None:
        with self._lock:
            pools = self._retired + ([self._pool] if self._pool is not None else [])
            self._retired = []
            self._pool = None
        for pool in pools:
            pool.shutdown(wait=True, cancel_futures=True)


_conversion = _Workers()
_thumbnails = _Workers()


def configure_workers(conversion: int | None, thumbnails: int | None) -> None:
    _conversion.configure(conversion)
    _thumbnails.configure(thumbnails)


def conversion_workers() -> int:
    return _conversion.count


def thumbnail_workers() -> int:
    return _thumbnails.count


def thumbnail_limit() -> Limiter:
    return _thumbnails.limiter


def _get_pool(
    kind: Literal["conversion", "thumbnail"] = "conversion",
) -> ProcessPoolExecutor | None:
    return (_conversion if kind == "conversion" else _thumbnails).pool()


def shutdown() -> None:
    _conversion.shutdown()
    _thumbnails.shutdown()


def _result(future: Future[bytes]) -> bytes:
    while True:
        checkpoint()
        try:
            return future.result(timeout=0.1)
        except TimeoutError:
            # A completed job may itself have raised TimeoutError. Propagate it
            # instead of mistaking it for a polling timeout forever.
            if future.done():
                return future.result()
            continue


def encode_pages(raws: Iterable[bytes], *, quality: int | None = None) -> Generator[bytes]:
    """Keep a bounded ordered window; total submissions share the conversion limiter."""
    source = iter(raws)
    pending: list[Future[bytes]] = []
    try:
        exhausted = False
        while True:
            while not exhausted and len(pending) < conversion_workers():
                checkpoint()
                raw = next(source, None)
                if raw is None:
                    exhausted = True
                    break
                pending.append(_conversion.submit(partial(encode_bytes, raw, quality=quality)))
            if not pending:
                break
            result = _result(pending[0])
            pending.pop(0)
            yield result
            checkpoint()
    finally:
        for future in pending:
            future.cancel()
        for future in pending:
            if not future.cancelled():
                with suppress(Exception):
                    future.result()


def _thumbnail(
    source: bytes | Image.Image,
    edge: int,
    content_class: ContentClass,
    quality: int | None,
    aspect: float | None = None,
) -> bytes:
    image = load_image(source).copy()
    if aspect is None:
        image.thumbnail((edge, edge), resample=Image.Resampling.LANCZOS)
    else:
        width, height = edge, round(edge / aspect)
        scale = min(1.0, image.width / width, image.height / height)
        size = (max(1, int(width * scale)), max(1, int(height * scale)))
        image = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
    return encode(image, content_class=content_class, quality=quality)


def encode_thumbnail(
    source: bytes | Image.Image,
    edge: int,
    content_class: ContentClass,
    quality: int | None,
    *,
    aspect: float | None = None,
) -> bytes:
    """Covers and previews have their own CPU budget, independent of page conversion."""
    checkpoint()
    future = _thumbnails.submit(partial(_thumbnail, source, edge, content_class, quality, aspect))
    try:
        return _result(future)
    finally:
        if not future.done():
            future.cancel()
            if not future.cancelled():
                with suppress(Exception):
                    future.result()


_ = atexit.register(shutdown)
