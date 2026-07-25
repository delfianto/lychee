"""Parallel AVIF page encoding across a process pool.

``avif.encode`` is a pure function of its input, so a chapter's page encodes can be
fanned out across worker *processes* (each with its own GIL) to use every core. This is
enabled by ``settings.encode_workers`` > 1; otherwise pages encode serially in-process.

The pool is lazily created and shared across jobs (the task queue runs jobs serially, so
there's never concurrent use), and uses the ``spawn`` start method — forking a
multi-threaded app (SSE loop + queue worker) risks child deadlocks, and spawn re-imports
cleanly so the picklable ``encode_bytes`` target resolves in each worker.
"""

from __future__ import annotations

import atexit
import multiprocessing as mp
from collections.abc import Iterator
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from threading import Lock

from src.core.config import settings
from src.media.avif import encode_bytes

_pool: ProcessPoolExecutor | None = None
_lock = Lock()


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


def encode_pages(raws: list[bytes], *, quality: int | None = None) -> Iterator[bytes]:
    """Encode each page's raw bytes to AVIF, yielded **in page order**. Fans out across the
    process pool when enabled; otherwise encodes serially in-process. Encoding is
    deterministic, so the parallel and serial results are identical."""
    encode = partial(encode_bytes, quality=quality)
    pool = _get_pool()
    if pool is None:
        return (encode(raw) for raw in raws)
    return pool.map(encode, raws)
