"""Single-flight image publication shared by foreground and background callers."""

from collections.abc import Iterator
from contextlib import contextmanager
from threading import Lock

from src.tasks.context import checkpoint

_guard = Lock()
_locks: dict[str, tuple[Lock, int]] = {}


@contextmanager
def artifact_lock(key: str) -> Iterator[None]:
    with _guard:
        lock, users = _locks.get(key, (Lock(), 0))
        _locks[key] = (lock, users + 1)
    acquired = False
    try:
        while not acquired:
            checkpoint()
            acquired = lock.acquire(timeout=0.1)
        checkpoint()
        yield
    finally:
        if acquired:
            lock.release()
        with _guard:
            _, users = _locks[key]
            if users == 1:
                del _locks[key]
            else:
                _locks[key] = (lock, users - 1)
