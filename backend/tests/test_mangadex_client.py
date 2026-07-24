"""MangaDexClient: retry-on-429 + best-effort reporting (mock transport, no network)."""

import time

import httpx
from src.providers.mangadex_client import API_BASE, MangaDexClient


def _client(handler: httpx.MockTransport) -> MangaDexClient:
    return MangaDexClient(client=httpx.Client(base_url=API_BASE, transport=handler))


def test_get_retries_on_429_then_succeeds() -> None:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            # X-RateLimit-Retry-After is a UNIX timestamp; "now" ⇒ ~0s wait
            return httpx.Response(429, headers={"X-RateLimit-Retry-After": str(int(time.time()))})
        return httpx.Response(200, json={"data": []})

    api = _client(httpx.MockTransport(handler))
    response = api.get("/manga")
    assert response.status_code == 200
    assert calls["n"] == 2  # one 429, one success


def test_get_raises_after_exhausting_retries() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        # Always 429 with a "now" timestamp so the bounded retries wait ~0s.
        return httpx.Response(429, headers={"X-RateLimit-Retry-After": str(int(time.time()))})

    api = MangaDexClient(
        client=httpx.Client(base_url=API_BASE, transport=httpx.MockTransport(handler)),
        max_retries=1,
    )
    try:
        _ = api.get("/manga")
    except httpx.HTTPStatusError as exc:
        assert exc.response.status_code == 429
    else:  # pragma: no cover
        raise AssertionError("expected HTTPStatusError after retries")


def test_report_is_best_effort() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")  # even a transport error must be swallowed

    api = _client(httpx.MockTransport(handler))
    # Must not raise despite the failing transport.
    api.report("https://node/data/h/p.png", success=True, nbytes=10, duration_ms=5, cached=False)
