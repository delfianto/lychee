"""MCP orchestration through the real HTTP client and an offline transport."""

import json
from collections.abc import Callable

import httpx
import pytest
import pytest_asyncio
from src import client as client_module
from src.client import LycheeApiError, LycheeClient
from src.tools import downloads, libraries, series, taxonomy


def row(series_id: str, **overrides: object) -> dict[str, object]:
    return {
        "id": series_id,
        "title": series_id,
        "coverUrl": "/cover",
        "status": "ongoing",
        "contentRating": "safe",
        "demographic": "none",
        "chapterCount": 2,
        "unreadCount": 1,
        **overrides,
    }


@pytest_asyncio.fixture
async def transport(monkeypatch: pytest.MonkeyPatch):
    clients: list[LycheeClient] = []

    def install(handler: Callable[[httpx.Request], httpx.Response]) -> None:
        client = LycheeClient(base_url="http://test", transport=httpx.MockTransport(handler))
        clients.append(client)
        monkeypatch.setattr(client_module, "_client", client)

    yield install
    for client in clients:
        await client.aclose()


async def test_browse_filters_and_detail_preserve_wire_names(transport):
    requests: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/series/s1":
            return httpx.Response(200, json=row("s1", userRating=8.5))
        return httpx.Response(200, json={"items": [row("s1")], "nextCursor": "next"})

    transport(handle)
    result = await series.list_series(
        kind="comic",
        favorite=False,
        q="hello",
        tags="action,-horror",
        tag_mode="or",
        ratings="safe",
        demographics="shonen",
        pub_status="ongoing",
        read_state="unread",
        sort="title",
        limit=12,
        cursor="previous",
    )
    assert dict(requests[0].url.params) == {
        "kind": "comic",
        "favorite": "false",
        "q": "hello",
        "tags": "action,-horror",
        "tagMode": "or",
        "ratings": "safe",
        "demographics": "shonen",
        "pubStatus": "ongoing",
        "readState": "unread",
        "sort": "title",
        "limit": "12",
        "cursor": "previous",
    }
    assert result["nextCursor"] == "next"
    items = result["items"]
    assert isinstance(items, list)
    assert items[0]["unreadCount"] == 1
    assert "unread_count" not in items[0]
    assert (await series.get_series("s1"))["userRating"] == 8.5


async def test_detail_preserves_backend_errors(transport):
    transport(lambda request: httpx.Response(404, json={"error": {"message": "Missing series"}}))
    with pytest.raises(LycheeApiError, match="Missing series"):
        await series.get_series("missing")


@pytest.mark.parametrize(
    "tool,matched",
    [
        (
            series.find_untagged_series,
            {"tags": [{"id": "tag", "name": "Action", "group": "genre"}]},
        ),
        (series.find_unmatched_series, {"provider": "mangadex"}),
    ],
)
async def test_finders_follow_cursors_and_stop_at_result_limit(transport, tool, matched):
    cursors: list[str | None] = []

    def handle(request: httpx.Request) -> httpx.Response:
        cursor = request.url.params.get("cursor")
        cursors.append(cursor)
        assert request.url.params["kind"] == "manga"
        items = [row("skip", **matched), row("a")] if cursor is None else [row("b"), row("c")]
        return httpx.Response(
            200, json={"items": items, "nextCursor": "p2" if cursor is None else "p3"}
        )

    transport(handle)
    assert [item["id"] for item in await tool(kind="manga", max_items=2)] == ["a", "b"]
    assert cursors == [None, "p2"]


@pytest.mark.parametrize("tool", [series.find_untagged_series, series.find_unmatched_series])
async def test_finders_stop_on_exhaustion_and_zero_limit(transport, tool):
    calls: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json={"items": [], "nextCursor": None})

    transport(handle)
    assert await tool(max_items=0) == []
    assert calls == []
    assert await tool() == []
    assert len(calls) == 1


@pytest.mark.parametrize(
    "mode,expected",
    [
        ("add", ["existing", "shared", "new"]),
        ("remove", ["existing"]),
        ("replace", ["shared", "new"]),
    ],
)
async def test_tag_modes_deduplicate_preserve_order_and_continue_after_failure(
    transport, mode, expected
):
    reads: list[str] = []
    writes: dict[str, object] = {}

    def handle(request: httpx.Request) -> httpx.Response:
        series_id = request.url.path.rsplit("/", 1)[-1]
        if series_id == "bad":
            return httpx.Response(409, json={"error": {"message": "locked"}})
        if request.method == "GET":
            reads.append(series_id)
            return httpx.Response(
                200,
                json=row(
                    series_id,
                    tags=[
                        {"id": tag, "name": tag, "group": "genre"} for tag in ["existing", "shared"]
                    ],
                ),
            )
        writes[series_id] = json.loads(request.content)
        return httpx.Response(200, json=row(series_id))

    transport(handle)
    result = await series.bulk_tag_series(["first", "bad", "last"], ["shared", "new", "new"], mode)
    assert result["updated"] == ["first", "last"]
    failed = result["failed"]
    assert isinstance(failed, dict)
    assert "locked" in failed["bad"]
    assert writes == {"first": {"tagIds": expected}, "last": {"tagIds": expected}}
    assert reads == ([] if mode == "replace" else ["first", "last"])


@pytest.mark.parametrize(
    "tool,args,body,key",
    [
        (series.bulk_set_favorite, (False,), {"favorite": False}, "updated"),
        (series.bulk_set_library_status, ("reading",), {"libraryStatus": "reading"}, "updated"),
        (downloads.bulk_queue_downloads, (), None, "queued"),
    ],
)
async def test_bulk_writes_continue_after_a_rejected_item(transport, tool, args, body, key):
    requested: list[str] = []

    def handle(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        series_id = payload["seriesId"] if body is None else request.url.path.rsplit("/", 1)[-1]
        requested.append(series_id)
        if body is not None:
            assert payload == body
        if series_id == "bad":
            return httpx.Response(400, json={"error": {"message": "not available"}})
        return httpx.Response(200, json=row(series_id))

    transport(handle)
    result = await tool(["first", "bad", "last"], *args)
    assert result[key] == ["first", "last"]
    assert "not available" in result["failed"]["bad"]
    assert requested == ["first", "bad", "last"]


async def test_invalid_modes_fail_before_http(transport):
    def unexpected(request: httpx.Request) -> httpx.Response:
        raise AssertionError("invalid input must not make a request")

    transport(unexpected)
    with pytest.raises(ValueError, match="mode must"):
        await series.bulk_tag_series(["s1"], [], mode="invalid")
    with pytest.raises(ValueError, match="status must"):
        await series.bulk_set_library_status(["s1"], "invalid")


@pytest.mark.parametrize(
    "library_id,path", [(None, "/api/libraries/scan"), ("lib", "/api/libraries/lib/scan")]
)
async def test_scans_target_one_or_all_libraries(transport, library_id, path):
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" and request.url.path == path
        return httpx.Response(
            202,
            json={
                "id": "task",
                "kind": "scan",
                "label": "Scan",
                "status": "running",
                "progress": 0,
            },
        )

    transport(handle)
    assert (await libraries.scan_library(library_id))["status"] == "running"


async def test_libraries_and_downloads_keep_wire_names(transport):
    def handle(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/libraries":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "lib",
                        "name": "Manga",
                        "path": "/media",
                        "kind": "manga",
                        "enabled": True,
                        "seriesCount": 2,
                    }
                ],
            )
        assert request.url.path == "/api/downloads"
        return httpx.Response(
            200,
            json=[
                {
                    "id": "d",
                    "series": row("s1"),
                    "chapter": "1",
                    "status": "queued",
                    "progress": 0,
                    "sizeBytes": 512,
                }
            ],
        )

    transport(handle)
    assert (await libraries.list_libraries())[0]["seriesCount"] == 2
    assert (await downloads.list_downloads())[0]["sizeBytes"] == 512


async def test_taxonomy_filters_category_without_altering_ids(transport):
    def handle(request: httpx.Request) -> httpx.Response:
        assert request.url.params["pageSize"] == "500"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "id": cat,
                        "name": cat,
                        "category": cat,
                        "uses": 2,
                        "enabled": True,
                        "system": False,
                    }
                    for cat in ["genre", "theme"]
                ],
                "total": 2,
                "page": 1,
                "pageSize": 500,
            },
        )

    transport(handle)
    assert [item["id"] for item in await taxonomy.list_taxonomy()] == ["genre", "theme"]
    assert [item["id"] for item in await taxonomy.list_taxonomy("genre")] == ["genre"]
    assert await taxonomy.list_taxonomy("missing") == []
