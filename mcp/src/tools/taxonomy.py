"""Taxonomy (tag vocabulary) tools — resolve tag names to the ids bulk_tag_series expects."""

from __future__ import annotations

from ..app import mcp
from ..client import get_client


@mcp.tool
async def list_taxonomy(category: str | None = None) -> list[dict[str, object]]:
    """List the tag vocabulary (genre/theme/format/content tags) with usage
    counts. `category` filters to one of: genre, theme, format, content,
    content_rating, demographic. Use this to resolve tag names to the ids
    bulk_tag_series expects.
    """
    client = get_client()
    page = await client.list_taxonomy()
    items = page.items if category is None else [i for i in page.items if i.category == category]
    return [i.model_dump(by_alias=True) for i in items]
