"""Parallel AVIF page encoding across a process pool.

``avif.encode`` is a pure function of its input, so a chapter's page encodes can be
fanned out across worker *processes* (each with its own GIL) to use every core. This is
enabled by ``settings.encode_workers`` > 1; otherwise pages encode serially in-process.

The pool is lazily created and shared by page and thumbnail jobs, and uses the
``spawn`` start method — forking a
multi-threaded app (SSE loop + queue worker) risks child deadlocks, and spawn re-imports
cleanly so the picklable ``encode_bytes`` target resolves in each worker.
"""

from __future__ import annotations

import atexit
import multiprocessing as mp
from collections.abc import Generator, Iterable
from concurrent.futures import Future, ProcessPoolExecutor, TimeoutError
from contextlib import suppress
from functools import partial
from threading import Lock

from PIL import Image, ImageOps

from src.core.config import settings
from src.media.avif import ContentClass, encode, encode_bytes, load_image
from src.tasks.concurrency import Limiter
from src.tasks.context import checkpoint

_pool: ProcessPoolExecutor | None = None
_lock = Lock()
_serial_cpu = Limiter(1)


def _get_pool() -> ProcessPoolExecutor | None:
    """The shared encode pool, or None when parallel encoding is disabled (workers ≤ 1)."""
    if settings.encode_workers <= 1:
        return None
    global _pool
    with _lock:
        if _pool is None:
            _pool = ProcessPoolExecutor(
                max_workers=settings.encode_workers, mp_context=mp.get_context("spawn")
            )
            _ = atexit.register(shutdown)
    return _pool


def shutdown() -> None:
    """Tear down the shared pool (registered at exit; safe to call repeatedly)."""
    global _pool
    with _lock:
        if _pool is not None:
            _pool.shutdown(wait=False, cancel_futures=True)
            _pool = None


def _result(future: Future[bytes]) -> bytes:
    while True:
        checkpoint()
        try:
            return future.result(timeout=0.1)
        except TimeoutError:
            continue


def encode_pages(raws: Iterable[bytes], *, quality: int | None = None) -> Generator[bytes]:
    """Bounded page encoding in source order, cancelling queued work on early exit."""
    encode_page = partial(encode_bytes, quality=quality)
    pool = _get_pool()
    if pool is None:
        for raw in raws:
            checkpoint()
            with _serial_cpu.slot():
                result = encode_page(raw)
            yield result
        return
    source = iter(raws)
    pending: list[Future[bytes]] = []
    try:
        for _ in range(settings.encode_workers):
            checkpoint()
            raw = next(source, None)
            if raw is None:
                break
            pending.append(pool.submit(encode_page, raw))
        while pending:
            future = pending[0]
            result = _result(future)
            pending.pop(0)
            yield result
            checkpoint()
            raw = next(source, None)
            if raw is not None:
                pending.append(pool.submit(encode_page, raw))
    finally:
        for future in pending:
            future.cancel()
        # A parent is not stopped while a child still owns its image buffers.
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
    """Use the same global CPU pool for page conversion, covers and thumbnails."""
    checkpoint()
    pool = _get_pool()
    if pool is None:
        with _serial_cpu.slot():
            result = _thumbnail(source, edge, content_class, quality, aspect)
        checkpoint()
        return result
    future = pool.submit(_thumbnail, source, edge, content_class, quality, aspect)
    try:
        return _result(future)
    finally:
        if not future.done():
            future.cancel()
            if not future.cancelled():
                with suppress(Exception):
                    future.result()
