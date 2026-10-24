"""Server 'about' info — version, platform, database, and uptime."""

from __future__ import annotations

import platform
from datetime import UTC, datetime

from src.core.config import settings
from src.core.version import VERSION
from src.integrations.schema import AboutOut

_STARTED = datetime.now(UTC)


def info() -> AboutOut:
    now = datetime.now(UTC)
    return AboutOut(
        version=VERSION,
        platform=platform.platform(),
        database="Turso (local MVCC)"
        if settings.database_url.startswith("sqlite+turso:")
        else "SQLite",
        started=_STARTED,
        uptime_seconds=int((now - _STARTED).total_seconds()),
    )
