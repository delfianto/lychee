"""Bounded, cancellation-aware I/O fanout; callers retain ownership until workers stop."""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Generator, Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from contextvars import copy_context
from threading import Condition, local

from src.tasks.context import checkpoint


class Limiter:
    """A live concurrency limit; reducing it lets existing work drain."""

    def __init__(self, count: int, *, reentrant: bool = False, fifo: bool = False) -> None:
        self._reentrant = reentrant
        self.count = count
        self.active = 0
        self._condition = Condition()
        self._local = local()
        self._fifo = fifo
        self._waiting: deque[object] = deque()

    def resize(self, count: int) -> None:
        with self._condition:
            self.count = count
            self._condition.notify_all()

    @contextmanager
    def slot(self) -> Iterator[None]:
        # Nested metadata calls in the same thread reuse the permit. Thread-local
        # state deliberately does not propagate with copy_context to child workers.
        if self._reentrant and getattr(self._local, "held", False):
            checkpoint()
            yield
            return
        ticket = object()
        acquired = False
        if self._fifo:
            with self._condition:
                self._waiting.append(ticket)
        try:
            while True:
                checkpoint()
                with self._condition:
                    first = not self._fifo or self._waiting[0] is ticket
                    if self.active < self.count and first:
                        self.active += 1
                        acquired = True
                        if self._fifo:
                            self._waiting.popleft()
                        self._condition.notify_all()
                        break
                    self._condition.wait(timeout=0.1)
            if self._reentrant:
                self._local.held = True
            checkpoint()
            yield
        finally:
            if self._reentrant and acquired:
                self._local.held = False
            with self._condition:
                if acquired:
                    self.active -= 1
                elif self._fifo:
                    self._waiting.remove(ticket)
                self._condition.notify_all()


def parallel_map[T, R](
    work: Callable[[T], R],
    items: Iterable[T],
    *,
    workers: int,
    ordered: bool = False,
    limit: Limiter | None = None,
) -> Generator[R]:
    """Yield completed results, with at most ``workers`` jobs in flight.

    ``workers`` bounds executor capacity; an optional live limiter controls the
    submission window and is rechecked while existing work is blocked.

    Copy the operation context into workers. On cancellation/error, stop submission,
    cancel pending futures and join running work before the owner's workspace exits.
    """
    source = iter(items)
    pool = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="lychee-io")
    pending = []
    exhausted = False
    try:

        def submit_one() -> bool:
            checkpoint()
            try:
                item = next(source)
            except StopIteration:
                return False
            pending.append(pool.submit(copy_context().run, work, item))
            return True

        while True:
            checkpoint()
            target = min(max(1, workers), max(1, limit.count)) if limit else max(1, workers)
            while not exhausted and len(pending) < target:
                exhausted = not submit_one()
            if not pending:
                break
            targets = pending[:1] if ordered else pending
            done, _ = wait(targets, timeout=0.1, return_when=FIRST_COMPLETED)
            for future in done:
                pending.remove(future)
                yield future.result()
    finally:
        for future in pending:
            future.cancel()
        pool.shutdown(wait=True, cancel_futures=True)
