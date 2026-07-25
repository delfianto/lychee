"""Rate-limited, retrying HTTP client for the MangaDex API.

Wraps one ``httpx.Client`` with: a global ~5 req/s token bucket + a 40/min bucket
for the at-home server endpoint; 429 handling that honours ``X-RateLimit-Retry-
After`` (a UNIX timestamp); bounded retries with backoff on transient 5xx; the
required non-spoofed ``User-Agent``. Node image fetches (``get_bytes``) hit at-home
hosts and aren't counted against the api.mangadex.org buckets. ``report`` posts the
mandatory MangaDex@Home usage report best-effort — it never raises, so it can't
fail a download.

Note: never attach account auth to node or report requests — the
at-home network is third-party. Today no auth is set, so one client is safe;
when auth lands it must be applied per-request to api.mangadex.org calls only.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import httpx

from src.core.logging import get_logger
from src.providers.ratelimit import TokenBucket

logger = get_logger(__name__)

API_BASE = "https://api.mangadex.org"
REPORT_URL = "https://api.mangadex.network/report"
USER_AGENT = "lychee/0.0.1 (self-hosted manga server)"

_RETRY_STATUSES = {429, 502, 503, 504}
_MAX_RETRIES = 3
_MAX_WAIT = 60.0


class MangaDexClient:
    def __init__(
        self,
        client: httpx.Client | None = None,
        *,
        global_bucket: TokenBucket | None = None,
        athome_bucket: TokenBucket | None = None,
        max_retries: int = _MAX_RETRIES,
    ) -> None:
        self._client = client or httpx.Client(
            base_url=API_BASE, timeout=30.0, headers={"User-Agent": USER_AGENT}
        )
        self._global = global_bucket or TokenBucket(5.0, 5.0)
        self._athome = athome_bucket or TokenBucket(40 / 60, 40)
        self._max_retries = max_retries

    def get(
        self,
        path: str,
        *,
        params: dict[str, str | int | list[str]] | None = None,
        athome: bool = False,
    ) -> httpx.Response:
        """GET an api.mangadex.org path with rate limiting + retries."""

        def send() -> httpx.Response:
            self._global.acquire()
            if athome:
                self._athome.acquire()
            return self._client.get(path, params=params)

        return self._with_retries(send)

    def post(self, path: str, *, json: dict[str, object] | None = None) -> httpx.Response:
        """POST an api.mangadex.org path (rate limited + retried). Used for authed writes
        (status / read markers); the Bearer rides on the client and only api.mangadex.org
        paths go through here — never at-home nodes."""

        def send() -> httpx.Response:
            self._global.acquire()
            return self._client.post(path, json=json)

        return self._with_retries(send)

    def get_bytes(self, url: str) -> httpx.Response:
        """GET an absolute at-home node URL (image); not rate-limited here."""
        return self._with_retries(lambda: self._client.get(url))

    def _with_retries(self, send: Callable[[], httpx.Response]) -> httpx.Response:
        response = send()
        attempt = 0
        while response.status_code in _RETRY_STATUSES and attempt < self._max_retries:
            time.sleep(self._retry_wait(response, attempt))
            attempt += 1
            response = send()
        _ = response.raise_for_status()
        return response

    def _retry_wait(self, response: httpx.Response, attempt: int) -> float:
        if response.status_code == 429:
            header = response.headers.get("X-RateLimit-Retry-After", "")
            if header.isdigit():  # documented as a UNIX timestamp
                return min(_MAX_WAIT, max(0.0, float(header) - time.time()))
        return min(_MAX_WAIT, 0.5 * 2**attempt)  # exponential backoff for 5xx

    def report(
        self, url: str, *, success: bool, nbytes: int, duration_ms: int, cached: bool
    ) -> None:
        """Best-effort MangaDex@Home usage report; swallows every error."""
        try:
            _ = self._client.post(
                REPORT_URL,
                json={
                    "url": url,
                    "success": success,
                    "bytes": nbytes,
                    "duration": duration_ms,
                    "cached": cached,
                },
                timeout=5.0,
            )
        except Exception as exc:  # noqa: BLE001 - reporting must never break a download
            logger.debug("athome_report_failed", error=str(exc))
