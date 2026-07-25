"""Server 'about' info — version, platform, database, and uptime."""

from __future__ import annotations

import platform
from datetime import UTC, datetime

from src.integrations.schema import AboutOut

_STARTED = datetime.now(UTC)


def info() -> AboutOut:
    now = datetime.now(UTC)
    return AboutOut(
        version="0.0.1",
        platform=platform.platform(),
        database="SQLite",
        started=_STARTED,
        uptime_seconds=int((now - _STARTED).total_seconds()),
    )
