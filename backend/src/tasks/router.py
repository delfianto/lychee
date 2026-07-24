"""Tasks + SSE events API."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from src.tasks.events import broker
from src.tasks.schema import TaskOut
from src.tasks.tracker import tracker

router = APIRouter(prefix="/api", tags=["tasks"])


@router.get("/tasks")
def list_tasks() -> list[TaskOut]:
    """Snapshot of recent/running tasks."""
    return [TaskOut.model_validate(t) for t in tracker.snapshot()]


@router.get("/events")
async def events() -> StreamingResponse:
    """Server-Sent Events stream of task progress (scan/download/sync)."""

    async def stream() -> AsyncIterator[str]:
        yield ": connected\n\n"
        async for event in broker.subscribe():
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
