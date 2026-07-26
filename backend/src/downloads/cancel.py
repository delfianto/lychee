"""Cooperative download cancellation.

The serial drain loop checks :func:`is_cancelled` between chapters (and page
callbacks can raise :class:`DownloadCancelled` for a faster stop). Cancel-all and
deleting an in-flight row set the flag; a successful drain clears it.
"""

from __future__ import annotations

import threading

_lock = threading.Lock()
_cancelled_series: set[str] = set()


class DownloadCancelled(Exception):
    """Raised when a download is cancelled mid-chapter."""


def request_cancel(series_id: str) -> None:
    with _lock:
        _cancelled_series.add(series_id)


def request_cancel_many(series_ids: list[str]) -> None:
    with _lock:
        _cancelled_series.update(series_ids)


def clear_cancel(series_id: str) -> None:
    with _lock:
        _cancelled_series.discard(series_id)


def is_cancelled(series_id: str) -> bool:
    with _lock:
        return series_id in _cancelled_series


def check_cancelled(series_id: str) -> None:
    if is_cancelled(series_id):
        raise DownloadCancelled(f"download cancelled for series {series_id}")
