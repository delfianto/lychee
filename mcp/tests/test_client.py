"""Client-layer tests, offline via httpx.MockTransport — mirrors the pattern
backend's own MangaDex client tests use (canned responses, no network)."""

import json

import httpx
from src.client import LycheeApiError, LycheeClient, _error_message
from src.models import _to_camel


def test_to_camel_matches_backend_wire_format():
    assert _to_camel("library_status") == "libraryStatus"
    assert _to_camel("id") == "id"
    assert _to_camel("size_bytes") == "sizeBytes"


def test_error_message_prefers_domain_error_shape():
    request = httpx.Request("GET", "http://test/api/series/x")
    response = httpx.Response(
        404,
        json={"error": {"code": "series_not_found", "message": "Series not found."}},
        request=request,
    )
    assert "Series not found." in _error_message("GET", "/api/series/x", response)


def test_error_message_falls_back_to_validation_detail():
    request = httpx.Request("PATCH", "http://test/api/series/x")
    response = httpx.Response(422, json={"detail": [{"msg": "bad value"}]}, request=request)
    assert "bad value" in _error_message("PATCH", "/api/series/x", response)


async def test_list_series_maps_filters_to_query_params():
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(request.url.params)
        return httpx.Response(200, json={"items": [], "nextCursor": None})

    client = LycheeClient(base_url="http://test", transport=httpx.MockTransport(handler))
    page = await client.list_series(kind="manga", favorite=True, limit=10, cursor=None)
    assert page.items == []
    assert page.next_cursor is None
    assert captured["kind"] == "manga"
    assert captured["favorite"] == "true"
    assert captured["limit"] == "10"
    assert "cursor" not in captured  # None values are dropped, not sent as "None"
    await client.aclose()


async def test_get_series_raises_lychee_api_error_with_backend_message():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            404, json={"error": {"code": "series_not_found", "message": "Series not found."}}
        )

    client = LycheeClient(base_url="http://test", transport=httpx.MockTransport(handler))
    try:
        await client.get_series("nope")
    except LycheeApiError as exc:
        assert "Series not found." in str(exc)
    else:
        raise AssertionError("expected LycheeApiError")
    await client.aclose()


async def test_patch_series_drops_none_fields_and_maps_camelcase():
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "id": "s1",
                "title": "Test",
                "coverUrl": "/api/series/s1/cover",
                "authors": [],
                "artists": [],
                "status": "ongoing",
                "contentRating": "safe",
                "demographic": "none",
                "tags": [],
                "chapterCount": 0,
                "unreadCount": 0,
                "favorite": True,
                "availableChapters": 0,
            },
        )

    client = LycheeClient(base_url="http://test", transport=httpx.MockTransport(handler))
    series = await client.patch_series(
        "s1", favorite=True, libraryStatus=None, tagIds=["genre-action"]
    )
    assert series.favorite is True
    assert captured == {"favorite": True, "tagIds": ["genre-action"]}
    await client.aclose()
