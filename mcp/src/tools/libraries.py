"""Library tools — list configured libraries, trigger scans."""

from __future__ import annotations

from ..app import mcp
from ..client import get_client


@mcp.tool
async def list_libraries() -> list[dict[str, object]]:
    """List configured libraries (manga/comics/gallery folders) and their scan status."""
    client = get_client()
    rows = await client.list_libraries()
    return [r.model_dump(by_alias=True) for r in rows]


@mcp.tool
async def scan_library(library_id: str | None = None) -> dict[str, object]:
    """Trigger a library scan. Omit `library_id` to scan every enabled
    library at once. Returns the queued task (status/progress); the scan
    itself runs in the background on the server.
    """
    client = get_client()
    task = (
        await client.scan_library(library_id) if library_id else await client.scan_all_libraries()
    )
    return task.model_dump(by_alias=True)
