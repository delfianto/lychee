"""SSE event broker — thread-safe publish, async subscribe (ADR 08/15).

Long-running work (scan/download/sync) runs in request/worker threads and calls
``publish`` (thread-safe); browser clients on ``GET /api/events`` consume via
``subscribe``. ``publish`` is a no-op until a running loop is bound at startup, so
it's safe to call from anywhere (including tests with no SSE clients).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Any


class EventBroker:
    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._subscribers: set[asyncio.Queue[dict[str, Any]]] = set()

    def bind_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def subscribe(self) -> AsyncGenerator[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subscribers.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._subscribers.discard(queue)

    def publish(self, event: dict[str, Any]) -> None:
        loop = self._loop
        if loop is None or loop.is_closed():
            return
        for queue in list(self._subscribers):
            loop.call_soon_threadsafe(queue.put_nowait, event)


broker = EventBroker()
