"""Download-queue tools — bulk-queue chapters, check queue status."""

from __future__ import annotations

from ..app import mcp
from ..client import get_client


@mcp.tool
async def bulk_queue_downloads(series_ids: list[str]) -> dict[str, object]:
    """Queue every available (not-yet-downloaded) chapter for a batch of
    series. Mirrors clicking "Download available" on each series' page.
    Failures on individual series don't abort the batch.
    """
    client = get_client()
    queued: list[str] = []
    failed: dict[str, str] = {}
    for series_id in series_ids:
        try:
            await client.queue_download(series_id)
            queued.append(series_id)
        except Exception as exc:  # noqa: BLE001 — report per-item failure, don't abort the batch
            failed[series_id] = str(exc)
    return {"queued": queued, "failed": failed}


@mcp.tool
async def list_downloads() -> list[dict[str, object]]:
    """List the current download queue (queued/downloading/paused/done/failed)."""
    client = get_client()
    tasks = await client.list_downloads()
    return [t.model_dump(by_alias=True) for t in tasks]
