"""Async HTTP client over the lychee backend's REST API.

This server is a *client* of the existing API (the same relationship the
frontend has), not a direct consumer of the backend's ORM/service layer —
see notes/plan.md PART J for why. No auth: the backend runs open/local
(ADR 12), and this client just talks to it like the webapp does.
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from .models import DownloadTask, LibraryRow, Series, SeriesPage, TaskOut, TaxonomyPage
from .settings import settings

# Query params are always primitives; PATCH/POST bodies here also carry the
# occasional string list (e.g. tagIds).
JsonPrimitive = str | int | float | bool | None
JsonValue = JsonPrimitive | list[str]


class LycheeApiError(RuntimeError):
    """Raised when the backend returns an error response.

    Carries the backend's own `{"error": {"code", "message"}}` message
    (see backend/AGENTS.md) so a failure surfaces something an agent can
    actually act on, not just an HTTP status code.
    """


def _error_message(method: str, path: str, response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"{method} {path} -> {response.status_code}: {response.text[:200]}"
    message: object = None
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            message = error.get("message")
        message = message or body.get("detail")
    return f"{method} {path} -> {response.status_code}: {message or body}"


class LycheeClient:
    def __init__(
        self,
        base_url: str | None = None,
        timeout: float = 30.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        # `transport` is a testing seam — inject an `httpx.MockTransport` to
        # exercise this client with canned responses, no live backend needed
        # (same pattern the backend's own MangaDex client tests use).
        self._http = httpx.AsyncClient(
            base_url=base_url or settings.lychee_api_url, timeout=timeout, transport=transport
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, JsonPrimitive] | None = None,
        json: Mapping[str, JsonValue] | None = None,
    ) -> httpx.Response:
        response = await self._http.request(method, path, params=params, json=json)
        if response.status_code >= 400:
            raise LycheeApiError(_error_message(method, path, response))
        return response

    # --- series -------------------------------------------------------------

    async def list_series(self, **params: JsonPrimitive) -> SeriesPage:
        query = {k: v for k, v in params.items() if v is not None}
        response = await self._request("GET", "/api/series", params=query)
        return SeriesPage.model_validate(response.json())

    async def get_series(self, series_id: str) -> Series:
        response = await self._request("GET", f"/api/series/{series_id}")
        return Series.model_validate(response.json())

    async def patch_series(self, series_id: str, **fields: JsonValue) -> Series:
        body = {k: v for k, v in fields.items() if v is not None}
        response = await self._request("PATCH", f"/api/series/{series_id}", json=body)
        return Series.model_validate(response.json())

    # --- taxonomy -------------------------------------------------------------

    async def list_taxonomy(self, page_size: int = 500) -> TaxonomyPage:
        response = await self._request("GET", "/api/taxonomy", params={"pageSize": page_size})
        return TaxonomyPage.model_validate(response.json())

    # --- downloads -------------------------------------------------------------

    async def queue_download(self, series_id: str) -> None:
        await self._request("POST", "/api/downloads", json={"seriesId": series_id})

    async def list_downloads(self) -> list[DownloadTask]:
        response = await self._request("GET", "/api/downloads")
        return [DownloadTask.model_validate(row) for row in response.json()]

    # --- libraries -------------------------------------------------------------

    async def list_libraries(self) -> list[LibraryRow]:
        response = await self._request("GET", "/api/libraries")
        return [LibraryRow.model_validate(row) for row in response.json()]

    async def scan_library(self, library_id: str) -> TaskOut:
        response = await self._request("POST", f"/api/libraries/{library_id}/scan")
        return TaskOut.model_validate(response.json())

    async def scan_all_libraries(self) -> TaskOut:
        response = await self._request("POST", "/api/libraries/scan")
        return TaskOut.model_validate(response.json())


_client: LycheeClient | None = None


def get_client() -> LycheeClient:
    """The shared client instance — one per process, matching how a stdio-run
    MCP server lives for the duration of a single agent session."""
    global _client
    if _client is None:
        _client = LycheeClient()
    return _client
