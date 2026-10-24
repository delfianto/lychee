"""Keep file fetching independent of CPU conversion without sharing ORM sessions."""

from __future__ import annotations

from collections.abc import Callable, Generator, Iterable
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from contextvars import copy_context
from pathlib import Path
from queue import Empty, SimpleQueue
from threading import Event, get_ident

from src.tasks.context import OperationCancelled, checkpoint, current_operation


class FetchProgress:
    """Workers post counters; only their owner invokes the database/UI callback."""

    def __init__(self, apply: Callable[[int, int], None]) -> None:
        self._owner = get_ident()
        self._apply = apply
        self._events: SimpleQueue[tuple[int, int]] = SimpleQueue()
        self._draining = False

    def post(self, done: int, total: int) -> None:
        self._events.put((done, total))
        self.drain()

    def drain(self) -> None:
        if get_ident() != self._owner or self._draining:
            return
        self._draining = True
        try:
            latest = None
            while True:
                try:
                    latest = self._events.get_nowait()
                except Empty:
                    break
            if latest is not None:
                self._apply(*latest)
        finally:
            self._draining = False


def prefetch_pages(source: Iterable[Path], tick: Callable[[], None]) -> Generator[Path]:
    """Spool source files while conversion runs. The queue holds paths, never image bytes.

    Network buffers remain bounded by the provider's file limiter. The producer
    owns and closes the source generator; its owner joins it before removing staging.
    """
    ready: SimpleQueue[Path | None] = SimpleQueue()
    stop = Event()

    def produce() -> None:
        try:
            for path in source:
                checkpoint()
                if stop.is_set():
                    break
                ready.put(path)
        finally:
            try:
                close = getattr(source, "close", None)
                if close is not None:
                    close()
            finally:
                ready.put(None)

    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="lychee-fetch")
    future: Future[None] | None = None
    operation = current_operation.get()
    if operation is not None:
        operation.checks.append(tick)
    try:
        future = pool.submit(copy_context().run, produce)
        while True:
            checkpoint()
            tick()
            try:
                path = ready.get(timeout=0.1)
            except Empty:
                continue
            if path is None:
                future.result()
                tick()
                break
            yield path
    finally:
        stop.set()
        if future is not None:
            future.cancel()
        pool.shutdown(wait=True, cancel_futures=True)
        try:
            with suppress(OperationCancelled):
                tick()
        finally:
            if operation is not None:
                operation.checks.remove(tick)
