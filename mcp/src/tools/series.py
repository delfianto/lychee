"""Series lookup + bulk-edit tools — thin wrappers over /api/series, plus the
orchestration (fetch-then-patch, paginate-then-filter) that endpoint doesn't
do by itself. See notes/plan.md PART J: v1 needs no backend changes — every
field these tools write already exists on SeriesUpdate.
"""

from __future__ import annotations

from ..app import mcp
from ..client import JsonValue, get_client

_LIBRARY_STATUSES = {
    "none",
    "reading",
    "on_hold",
    "dropped",
    "plan_to_read",
    "completed",
    "re_reading",
}


@mcp.tool
async def list_series(
    kind: str | None = None,
    favorite: bool | None = None,
    q: str | None = None,
    tags: str | None = None,
    tag_mode: str | None = None,
    ratings: str | None = None,
    demographics: str | None = None,
    pub_status: str | None = None,
    read_state: str | None = None,
    sort: str = "recentlyAdded",
    limit: int = 24,
    cursor: str | None = None,
) -> dict[str, object]:
    """Browse/filter the library's series (manga, comics, or galleries).

    Mirrors the webapp's library grid filters. `kind`: manga|comic|gallery.
    `tags`: comma-separated tag ids, prefix with "-" to exclude (see
    list_taxonomy for ids). `ratings`/`demographics`/`pub_status`: comma-
    separated value lists. `read_state`: unread|in_progress|read. Returns a
    page of series plus a `nextCursor` to pass back in for more. Use this to
    find candidate series ids before calling a bulk_* tool on them.
    """
    client = get_client()
    page = await client.list_series(
        kind=kind,
        favorite=favorite,
        q=q,
        tags=tags,
        tagMode=tag_mode,
        ratings=ratings,
        demographics=demographics,
        pubStatus=pub_status,
        readState=read_state,
        sort=sort,
        limit=limit,
        cursor=cursor,
    )
    return page.model_dump(by_alias=True)


@mcp.tool
async def get_series(series_id: str) -> dict[str, object]:
    """Fetch full detail for one series by id."""
    client = get_client()
    series = await client.get_series(series_id)
    return series.model_dump(by_alias=True)


@mcp.tool
async def find_untagged_series(
    kind: str | None = None, max_items: int = 500
) -> list[dict[str, object]]:
    """Find series with zero tags assigned — candidates for bulk_tag_series.

    Paginates through the library (capped at `max_items`, default 500) and
    returns full series objects for every one with an empty tag list.
    """
    client = get_client()
    out: list[dict[str, object]] = []
    cursor: str | None = None
    while len(out) < max_items:
        page = await client.list_series(kind=kind, limit=100, cursor=cursor)
        out.extend(s.model_dump(by_alias=True) for s in page.items if not s.tags)
        if not page.next_cursor:
            break
        cursor = page.next_cursor
    return out[:max_items]


@mcp.tool
async def find_unmatched_series(
    kind: str = "manga", max_items: int = 500
) -> list[dict[str, object]]:
    """Find series with no metadata-provider match — candidates for matching
    on MangaDex via the webapp (matching itself isn't exposed here yet; this
    just finds the backlog). `kind` defaults to "manga" since matching only
    applies there today.
    """
    client = get_client()
    out: list[dict[str, object]] = []
    cursor: str | None = None
    while len(out) < max_items:
        page = await client.list_series(kind=kind, limit=100, cursor=cursor)
        out.extend(s.model_dump(by_alias=True) for s in page.items if not s.provider)
        if not page.next_cursor:
            break
        cursor = page.next_cursor
    return out[:max_items]


async def _bulk_patch(series_ids: list[str], **fields: JsonValue) -> dict[str, object]:
    client = get_client()
    updated: list[str] = []
    failed: dict[str, str] = {}
    for series_id in series_ids:
        try:
            await client.patch_series(series_id, **fields)
            updated.append(series_id)
        except Exception as exc:  # noqa: BLE001 — report per-item failure, don't abort the batch
            failed[series_id] = str(exc)
    return {"updated": updated, "failed": failed}


@mcp.tool
async def bulk_tag_series(
    series_ids: list[str], tag_ids: list[str], mode: str = "add"
) -> dict[str, object]:
    """Add, remove, or replace tags on a batch of series in one call.

    `mode`: "add" (union with each series' existing tags), "remove"
    (subtract from existing tags), or "replace" (set exactly these tag ids,
    dropping any others). Tag ids come from list_taxonomy. Failures on
    individual series don't abort the batch — check the `failed` map in the
    result.
    """
    if mode not in ("add", "remove", "replace"):
        raise ValueError('mode must be "add", "remove", or "replace"')
    client = get_client()
    updated: list[str] = []
    failed: dict[str, str] = {}
    for series_id in series_ids:
        try:
            if mode == "replace":
                new_tag_ids = list(dict.fromkeys(tag_ids))
            else:
                current = await client.get_series(series_id)
                current_ids = [t.id for t in current.tags]
                if mode == "add":
                    new_tag_ids = list(dict.fromkeys([*current_ids, *tag_ids]))
                else:  # remove
                    drop = set(tag_ids)
                    new_tag_ids = [t for t in current_ids if t not in drop]
            await client.patch_series(series_id, tagIds=new_tag_ids)
            updated.append(series_id)
        except Exception as exc:  # noqa: BLE001 — report per-item failure, don't abort the batch
            failed[series_id] = str(exc)
    return {"updated": updated, "failed": failed}


@mcp.tool
async def bulk_set_favorite(series_ids: list[str], favorite: bool) -> dict[str, object]:
    """Mark or unmark a batch of series as favorites."""
    return await _bulk_patch(series_ids, favorite=favorite)


@mcp.tool
async def bulk_set_library_status(series_ids: list[str], status: str) -> dict[str, object]:
    """Set the reading-shelf status for a batch of series.

    `status` must be one of: none, reading, on_hold, dropped, plan_to_read,
    completed, re_reading.
    """
    if status not in _LIBRARY_STATUSES:
        raise ValueError(f"status must be one of {sorted(_LIBRARY_STATUSES)}")
    return await _bulk_patch(series_ids, libraryStatus=status)
