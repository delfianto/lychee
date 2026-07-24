"""Tests for the task tracker + SSE events."""

import asyncio
import io
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from PIL import Image
from src.main import app
from src.tasks.events import broker


def _scan_a_library(client: TestClient, tmp_path: Path) -> None:
    series_dir = tmp_path / "lib" / "Series A"
    series_dir.mkdir(parents=True)
    for i in range(2):
        buf = io.BytesIO()
        Image.new("RGB", (20, 30), (i * 40, 80, 120)).save(buf, "PNG")
        _ = (series_dir / f"{i + 1:03d}.png").write_bytes(buf.getvalue())
    created = client.post(
        "/api/libraries", json={"name": "T", "path": str(tmp_path / "lib"), "kind": "manga"}
    )
    _ = client.post(f"/api/libraries/{created.json()['id']}/scan")


def test_scan_records_a_completed_task(client: TestClient, tmp_path: Path) -> None:
    _scan_a_library(client, tmp_path)
    tasks = client.get("/api/tasks").json()
    scans = [t for t in tasks if t["kind"] == "scan"]
    assert scans
    assert any(t["status"] == "done" and t["progress"] == 100 for t in scans)


def test_broker_delivers_events_to_subscribers() -> None:
    """The SSE broker delivers a thread-safe publish to an async subscriber."""

    async def go() -> dict[str, Any]:
        broker.bind_loop(asyncio.get_running_loop())
        stream = broker.subscribe()
        pending = asyncio.ensure_future(anext(stream))
        await asyncio.sleep(0.01)  # let the subscriber register
        broker.publish({"event": "test.ping", "task": {"id": "x"}})
        event = await asyncio.wait_for(pending, timeout=1.0)
        await stream.aclose()
        return event

    assert asyncio.run(go())["event"] == "test.ping"


def test_events_route_registered() -> None:
    # Full SSE streaming can't be consumed by TestClient (infinite stream); just
    # confirm the route exists. Live behaviour is exercised via the broker test.
    assert "/api/events" in app.openapi()["paths"]
