"""Bounded, cancellation-aware I/O fanout; callers retain ownership until workers stop."""

from __future__ import annotations

from collections.abc import Callable, Generator, Iterable, Iterator
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import contextmanager
from contextvars import copy_context
from threading import Condition

from src.tasks.context import checkpoint


class Limiter:
    """A live concurrency limit; reducing it lets existing work drain."""

    def __init__(self, count: int) -> None:
        self.count = count
        self.active = 0
        self._condition = Condition()

    def resize(self, count: int) -> None:
        with self._condition:
            self.count = count
            self._condition.notify_all()

    @contextmanager
    def slot(self) -> Iterator[None]:
        while True:
            checkpoint()
            with self._condition:
                if self.active < self.count:
                    self.active += 1
                    break
                self._condition.wait(timeout=0.1)
        try:
            checkpoint()
            yield
        finally:
            with self._condition:
                self.active -= 1
                self._condition.notify_all()


def parallel_map[T, R](
    work: Callable[[T], R], items: Iterable[T], *, workers: int, ordered: bool = False
) -> Generator[R]:
    """Yield completed results, with at most ``workers`` jobs in flight.

    Copy the operation context into workers. On cancellation/error, stop submission,
    cancel pending futures and join running work before the owner's workspace exits.
    """
    source = iter(items)
    pool = ThreadPoolExecutor(max_workers=max(1, workers), thread_name_prefix="lychee-io")
    pending = []
    try:

        def submit_one() -> bool:
            checkpoint()
            try:
                item = next(source)
            except StopIteration:
                return False
            pending.append(pool.submit(copy_context().run, work, item))
            return True

        for _ in range(max(1, workers)):
            if not submit_one():
                break
        while pending:
            checkpoint()
            targets = pending[:1] if ordered else pending
            done, _ = wait(targets, timeout=0.1, return_when=FIRST_COMPLETED)
            for future in done:
                pending.remove(future)
                yield future.result()
                submit_one()
    finally:
        for future in pending:
            future.cancel()
        pool.shutdown(wait=True, cancel_futures=True)
